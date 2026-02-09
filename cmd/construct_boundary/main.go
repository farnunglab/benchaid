package main

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	defaultMinLength       = 100
	cacheTTL               = 30 * 24 * time.Hour
	uniprotBaseURL         = "https://rest.uniprot.org/uniprotkb"
	uniprotSearchURL       = "https://rest.uniprot.org/uniprotkb/search"
	alphafoldPredictionURL = "https://alphafold.ebi.ac.uk/api/prediction"
)

type cacheEntry struct {
	FetchedAt time.Time       `json:"fetched_at"`
	Payload   json.RawMessage `json:"payload"`
}

type uniProtEntry struct {
	PrimaryAccession   string                 `json:"primaryAccession"`
	UniProtKBID        string                 `json:"uniProtkbId"`
	ProteinDescription proteinDescription     `json:"proteinDescription"`
	Genes              []geneInfo             `json:"genes"`
	Sequence           uniProtSequence        `json:"sequence"`
	Features           []uniProtFeature       `json:"features"`
	CrossReferences    []uniProtCrossRef      `json:"uniProtKBCrossReferences"`
	Keywords           []map[string]string    `json:"keywords"`
	Extra              map[string]interface{} `json:"-"`
}

type proteinDescription struct {
	RecommendedName struct {
		FullName struct {
			Value string `json:"value"`
		} `json:"fullName"`
	} `json:"recommendedName"`
}

type geneInfo struct {
	GeneName struct {
		Value string `json:"value"`
	} `json:"geneName"`
}

type uniProtSequence struct {
	Value  string `json:"value"`
	Length int    `json:"length"`
}

type uniProtFeature struct {
	Type        string            `json:"type"`
	Description string            `json:"description"`
	Location    uniProtLocation   `json:"location"`
	Properties  map[string]string `json:"properties"`
}

type uniProtLocation struct {
	Start    *positionValue `json:"start"`
	End      *positionValue `json:"end"`
	Position *positionValue `json:"position"`
}

type positionValue struct {
	Value int `json:"value"`
}

type uniProtCrossRef struct {
	Database   string      `json:"database"`
	ID         string      `json:"id"`
	Properties propertyMap `json:"properties"`
}

type propertyMap map[string]string

func (p *propertyMap) UnmarshalJSON(data []byte) error {
	if len(data) == 0 || string(data) == "null" {
		return nil
	}
	if data[0] == '{' {
		var values map[string]string
		if err := json.Unmarshal(data, &values); err != nil {
			return err
		}
		*p = values
		return nil
	}
	if data[0] == '[' {
		var entries []map[string]string
		if err := json.Unmarshal(data, &entries); err != nil {
			return err
		}
		values := make(map[string]string)
		for _, entry := range entries {
			key := entry["key"]
			if key == "" {
				key = entry["property"]
			}
			if key == "" {
				continue
			}
			values[key] = entry["value"]
		}
		*p = values
		return nil
	}
	return errors.New("unknown properties format in UniProt cross-reference")
}

type alphaFoldPrediction struct {
	UniProtAccession string    `json:"uniprotAccession"`
	Plddt            []float64 `json:"plddt"`
	PdbURL           string    `json:"pdbUrl"`
	PaedocURL        string    `json:"paeDocUrl"`
}

type rangeInfo struct {
	Start  int
	End    int
	Name   string
	Type   string
	Source string
}

type pdbRange struct {
	ID         string
	Start      int
	End        int
	Method     string
	Resolution string
}

type prediction struct {
	Rank      int      `json:"rank"`
	Start     int      `json:"start"`
	End       int      `json:"end"`
	Length    int      `json:"length"`
	Score     float64  `json:"score"`
	Rationale string   `json:"rationale"`
	Evidence  evidence `json:"evidence"`
}

type evidence struct {
	PDBMatch         string  `json:"pdb_match,omitempty"`
	Domain           string  `json:"domain,omitempty"`
	AvgPLDDT         float64 `json:"avg_plddt,omitempty"`
	DisorderFraction float64 `json:"disorder_fraction,omitempty"`
}

type proteinSummary struct {
	UniProtID string `json:"uniprot_id,omitempty"`
	Name      string `json:"name,omitempty"`
	Length    int    `json:"length"`
	Gene      string `json:"gene,omitempty"`
}

type jsonOutput struct {
	Protein     proteinSummary `json:"protein"`
	Predictions []prediction   `json:"predictions"`
	Features    featureSummary `json:"features"`
	Warnings    []string       `json:"warnings,omitempty"`
}

type featureSummary struct {
	Domains           []rangeInfo `json:"domains"`
	DisorderedRegions []rangeInfo `json:"disordered_regions"`
	PDBStructures     []pdbRange  `json:"pdb_structures"`
	PLDDTScores       []float64   `json:"plddt_scores,omitempty"`
}

type boundaryContext struct {
	Length       int
	Disorder     []bool
	PLDDT        []float64
	DomainRanges []rangeInfo
	PDBRanges    []pdbRange
	HelixRanges  []rangeInfo
	StrandRanges []rangeInfo
	ActiveSites  []rangeInfo
	PTMPositions []int
}

type candidate struct {
	Start     int
	End       int
	Source    string
	Name      string
	PDBID     string
	Score     float64
	Rationale []string
	Evidence  evidence
}

func main() {
	var (
		identifier string
		sequence   string
		name       string
		region     string
		minLength  int
		maxLength  int
		jsonOut    bool
		plotPath   string
	)

	flag.StringVar(&identifier, "uniprot", "", "UniProt ID, entry name, or gene name")
	flag.StringVar(&sequence, "sequence", "", "Raw amino acid sequence")
	flag.StringVar(&name, "name", "", "Protein name (required with --sequence)")
	flag.StringVar(&region, "region", "", "Focus region (e.g., 500-800 or domain name)")
	flag.IntVar(&minLength, "min-length", defaultMinLength, "Minimum construct length (aa)")
	flag.IntVar(&maxLength, "max-length", 0, "Maximum construct length (aa, 0 for no limit)")
	flag.BoolVar(&jsonOut, "json", false, "Output JSON")
	flag.StringVar(&plotPath, "plot", "", "Write ASCII visualization to a file")
	flag.Parse()

	if sequence == "" && identifier == "" {
		fatalf("provide --uniprot or --sequence")
	}
	if sequence != "" && name == "" {
		fatalf("provide --name with --sequence")
	}
	if minLength <= 0 {
		minLength = defaultMinLength
	}

	cacheDir := defaultCacheDir()
	client := &http.Client{Timeout: 20 * time.Second}
	var warnings []string
	warnings = append(warnings, "IUPred/PSIPRED not integrated; loop detection uses pLDDT and UniProt secondary structure when available.")

	var entry uniProtEntry
	if sequence == "" {
		var err error
		entry, warnings, err = fetchUniProtEntry(client, cacheDir, identifier)
		if err != nil {
			fatalf("failed to fetch UniProt entry: %v", err)
		}
		sequence = entry.Sequence.Value
		if name == "" {
			name = entry.UniProtKBID
			if name == "" {
				name = entry.PrimaryAccession
			}
		}
	}

	sequence = sanitizeSequence(sequence)
	if sequence == "" {
		fatalf("sequence is empty after sanitization")
	}

	var plddt []float64
	if entry.PrimaryAccession != "" {
		var err error
		var afWarnings []string
		plddt, afWarnings, err = fetchAlphaFoldPLDDT(client, cacheDir, entry.PrimaryAccession)
		if err != nil {
			warnings = append(warnings, err.Error())
		}
		warnings = append(warnings, afWarnings...)
	}
	if len(plddt) > 0 && len(plddt) != len(sequence) {
		warnings = append(warnings, fmt.Sprintf("pLDDT length (%d) does not match sequence length (%d)", len(plddt), len(sequence)))
	}

	domains, helixes, strands, activeSites, ptmPositions := extractFeatures(entry.Features)
	pdbRanges := extractPDBRanges(entry.CrossReferences)
	disordered := computeDisorderedRegions(plddt, len(sequence))

	ctx := boundaryContext{
		Length:       len(sequence),
		Disorder:     disordered,
		PLDDT:        plddt,
		DomainRanges: domains,
		PDBRanges:    pdbRanges,
		HelixRanges:  helixes,
		StrandRanges: strands,
		ActiveSites:  activeSites,
		PTMPositions: ptmPositions,
	}

	regionRange, regionName, err := parseRegion(region)
	if err != nil {
		fatalf("invalid --region: %v", err)
	}

	candidates := buildCandidates(sequence, regionRange, regionName, domains, pdbRanges, disordered, minLength, maxLength)
	scored := scoreCandidates(candidates, ctx, minLength, maxLength)
	if len(scored) == 0 {
		fatalf("no construct candidates found with current filters")
	}
	sort.Slice(scored, func(i, j int) bool {
		if scored[i].Score == scored[j].Score {
			return scored[i].Length() < scored[j].Length()
		}
		return scored[i].Score > scored[j].Score
	})

	top := scored
	if len(top) > 10 {
		top = top[:10]
	}

	if jsonOut {
		out := jsonOutput{
			Protein: proteinSummary{
				UniProtID: entry.PrimaryAccession,
				Name:      name,
				Length:    len(sequence),
				Gene:      firstGene(entry.Genes),
			},
			Predictions: buildPredictions(top, plddt),
			Features: featureSummary{
				Domains:           domains,
				DisorderedRegions: compressDisorder(disordered),
				PDBStructures:     pdbRanges,
				PLDDTScores:       plddt,
			},
			Warnings: warnings,
		}
		if err := writeJSON(os.Stdout, out); err != nil {
			fatalf("failed to write JSON: %v", err)
		}
		return
	}

	printSummary(name, entry.PrimaryAccession, len(sequence), top, compressDisorder(disordered), pdbRanges, warnings)
	ascii := buildASCIIVisualization(len(sequence), plddt, disordered, domains, top)
	fmt.Println()
	fmt.Println(ascii)

	if plotPath != "" {
		if err := os.WriteFile(plotPath, []byte(ascii), 0644); err != nil {
			fatalf("failed to write plot: %v", err)
		}
	}
}

func defaultCacheDir() string {
	if cache := os.Getenv("XDG_CACHE_HOME"); cache != "" {
		return filepath.Join(cache, "benchaid")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "."
	}
	return filepath.Join(home, ".cache", "benchaid")
}

func sanitizeSequence(sequence string) string {
	sequence = strings.ToUpper(sequence)
	sequence = strings.ReplaceAll(sequence, " ", "")
	sequence = strings.ReplaceAll(sequence, "\n", "")
	sequence = strings.ReplaceAll(sequence, "\r", "")
	sequence = strings.ReplaceAll(sequence, "\t", "")
	return sequence
}

func fetchUniProtEntry(client *http.Client, cacheDir, identifier string) (uniProtEntry, []string, error) {
	var warnings []string
	body, err := fetchWithCache(client, cacheDir, "uniprot", identifier, func() ([]byte, error) {
		url := fmt.Sprintf("%s/%s.json", uniprotBaseURL, url.PathEscape(identifier))
		return httpGet(client, url)
	})
	if err == nil {
		entry, err := decodeUniProtEntry(body)
		return entry, warnings, err
	}

	searchBody, searchErr := fetchWithCache(client, cacheDir, "uniprot-search", identifier, func() ([]byte, error) {
		query := url.QueryEscape(fmt.Sprintf("gene_exact:%s OR %s", identifier, identifier))
		searchURL := fmt.Sprintf("%s?query=%s&format=json&size=5", uniprotSearchURL, query)
		return httpGet(client, searchURL)
	})
	if searchErr != nil {
		return uniProtEntry{}, warnings, err
	}

	accession, err := extractFirstAccession(searchBody)
	if err != nil {
		return uniProtEntry{}, warnings, err
	}
	warnings = append(warnings, fmt.Sprintf("resolved %q to UniProt accession %s", identifier, accession))

	entryBody, err := fetchWithCache(client, cacheDir, "uniprot", accession, func() ([]byte, error) {
		url := fmt.Sprintf("%s/%s.json", uniprotBaseURL, url.PathEscape(accession))
		return httpGet(client, url)
	})
	if err != nil {
		return uniProtEntry{}, warnings, err
	}
	entry, err := decodeUniProtEntry(entryBody)
	return entry, warnings, err
}

func decodeUniProtEntry(body []byte) (uniProtEntry, error) {
	var entry uniProtEntry
	normalized, err := normalizeJSON(body)
	if err != nil {
		return uniProtEntry{}, err
	}
	if err := json.Unmarshal(normalized, &entry); err != nil {
		return uniProtEntry{}, err
	}
	if entry.Sequence.Value == "" {
		return uniProtEntry{}, errors.New("missing sequence in UniProt response")
	}
	return entry, nil
}

func extractFirstAccession(body []byte) (string, error) {
	var resp struct {
		Results []struct {
			PrimaryAccession string `json:"primaryAccession"`
		} `json:"results"`
	}
	normalized, err := normalizeJSON(body)
	if err != nil {
		return "", err
	}
	if err := json.Unmarshal(normalized, &resp); err != nil {
		return "", err
	}
	if len(resp.Results) == 0 || resp.Results[0].PrimaryAccession == "" {
		return "", errors.New("no UniProt entries found")
	}
	return resp.Results[0].PrimaryAccession, nil
}

func fetchAlphaFoldPLDDT(client *http.Client, cacheDir, accession string) ([]float64, []string, error) {
	var warnings []string
	body, err := fetchWithCache(client, cacheDir, "alphafold", accession, func() ([]byte, error) {
		url := fmt.Sprintf("%s/%s", alphafoldPredictionURL, url.PathEscape(accession))
		return httpGet(client, url)
	})
	if err != nil {
		return nil, warnings, fmt.Errorf("alphafold lookup failed: %w", err)
	}
	var predictions []alphaFoldPrediction
	normalized, err := normalizeJSON(body)
	if err != nil {
		return nil, warnings, err
	}
	if err := json.Unmarshal(normalized, &predictions); err != nil {
		return nil, warnings, err
	}
	if len(predictions) == 0 {
		return nil, warnings, errors.New("alphafold response empty")
	}
	if len(predictions[0].Plddt) > 0 {
		return predictions[0].Plddt, warnings, nil
	}

	if predictions[0].PdbURL == "" {
		warnings = append(warnings, "AlphaFold model lacks pLDDT array and pdbUrl")
		return nil, warnings, nil
	}

	pdbBody, err := fetchWithCache(client, cacheDir, "alphafold-pdb", accession, func() ([]byte, error) {
		return httpGet(client, predictions[0].PdbURL)
	})
	if err != nil {
		return nil, warnings, err
	}
	plddt, err := parsePLDDTFromPDB(pdbBody)
	if err != nil {
		return nil, warnings, err
	}
	return plddt, warnings, nil
}

func parsePLDDTFromPDB(body []byte) ([]float64, error) {
	lines := strings.Split(string(body), "\n")
	var plddt []float64
	lastRes := -1
	for _, line := range lines {
		if !strings.HasPrefix(line, "ATOM") {
			continue
		}
		if len(line) < 66 {
			continue
		}
		atom := strings.TrimSpace(line[12:16])
		if atom != "CA" {
			continue
		}
		resSeqRaw := strings.TrimSpace(line[22:26])
		resSeq, err := strconv.Atoi(resSeqRaw)
		if err != nil {
			continue
		}
		if resSeq == lastRes {
			continue
		}
		lastRes = resSeq
		bFactorRaw := strings.TrimSpace(line[60:66])
		bFactor, err := strconv.ParseFloat(bFactorRaw, 64)
		if err != nil {
			continue
		}
		plddt = append(plddt, bFactor)
	}
	if len(plddt) == 0 {
		return nil, errors.New("no CA atoms found for pLDDT extraction")
	}
	return plddt, nil
}

func fetchWithCache(client *http.Client, cacheDir, namespace, key string, fetch func() ([]byte, error)) ([]byte, error) {
	cachePath := cacheFilePath(cacheDir, namespace, key)
	if payload, ok := readCache(cachePath); ok {
		return payload, nil
	}
	payload, err := fetch()
	if err != nil {
		return nil, err
	}
	if err := writeCache(cachePath, payload); err != nil {
		return payload, nil
	}
	return payload, nil
}

func cacheFilePath(cacheDir, namespace, key string) string {
	key = strings.ToLower(key)
	key = strings.ReplaceAll(key, "/", "_")
	key = strings.ReplaceAll(key, " ", "_")
	return filepath.Join(cacheDir, namespace, fmt.Sprintf("%s.json", key))
}

func readCache(path string) ([]byte, bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, false
	}
	var entry cacheEntry
	if err := json.Unmarshal(data, &entry); err != nil {
		return nil, false
	}
	if time.Since(entry.FetchedAt) > cacheTTL {
		return nil, false
	}
	return entry.Payload, true
}

func writeCache(path string, payload []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	entry := cacheEntry{
		FetchedAt: time.Now(),
		Payload:   payload,
	}
	data, err := json.MarshalIndent(entry, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

func httpGet(client *http.Client, url string) ([]byte, error) {
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		resp, err := client.Get(url)
		if err != nil {
			lastErr = err
			time.Sleep(time.Duration(attempt+1) * time.Second)
			continue
		}
		defer resp.Body.Close()
		if resp.StatusCode == http.StatusNotFound {
			return nil, fmt.Errorf("resource not found (%s)", url)
		}
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			lastErr = fmt.Errorf("http status %d", resp.StatusCode)
			time.Sleep(time.Duration(attempt+1) * time.Second)
			continue
		}
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			lastErr = err
			time.Sleep(time.Duration(attempt+1) * time.Second)
			continue
		}
		if resp.Header.Get("Content-Encoding") == "gzip" || isGzip(body) {
			decoded, err := gunzip(body)
			if err != nil {
				return nil, err
			}
			return decoded, nil
		}
		return body, nil
	}
	return nil, lastErr
}

func normalizeJSON(body []byte) ([]byte, error) {
	if isGzip(body) {
		return gunzip(body)
	}
	return body, nil
}

func isGzip(body []byte) bool {
	return len(body) >= 2 && body[0] == 0x1f && body[1] == 0x8b
}

func gunzip(body []byte) ([]byte, error) {
	reader, err := gzip.NewReader(bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	return io.ReadAll(reader)
}

func extractFeatures(features []uniProtFeature) (domains, helixes, strands, activeSites []rangeInfo, ptmPositions []int) {
	for _, feature := range features {
		start, end := featureRange(feature.Location)
		if start == 0 || end == 0 {
			continue
		}
		info := rangeInfo{
			Start:  start,
			End:    end,
			Name:   feature.Description,
			Type:   feature.Type,
			Source: "UniProt",
		}
		switch strings.ToUpper(feature.Type) {
		case "DOMAIN", "REGION", "REPEAT":
			domains = append(domains, info)
		case "HELIX":
			helixes = append(helixes, info)
		case "STRAND":
			strands = append(strands, info)
		case "ACT_SITE":
			activeSites = append(activeSites, info)
		case "MOD_RES", "CARBOHYD", "LIPID", "DISULFID", "CROSSLINK", "METAL":
			ptmPositions = append(ptmPositions, start)
		}
	}
	return domains, helixes, strands, activeSites, ptmPositions
}

func extractPDBRanges(crossRefs []uniProtCrossRef) []pdbRange {
	var ranges []pdbRange
	for _, ref := range crossRefs {
		if strings.ToUpper(ref.Database) != "PDB" {
			continue
		}
		chains := ref.Properties["Chains"]
		method := ref.Properties["Method"]
		resolution := ref.Properties["Resolution"]
		for _, chainPart := range strings.Split(chains, ",") {
			chainPart = strings.TrimSpace(chainPart)
			if chainPart == "" {
				continue
			}
			parts := strings.Split(chainPart, "=")
			if len(parts) != 2 {
				continue
			}
			for _, span := range strings.Split(parts[1], ",") {
				span = strings.TrimSpace(span)
				if span == "" {
					continue
				}
				rangeParts := strings.Split(span, "-")
				if len(rangeParts) != 2 {
					continue
				}
				start, err1 := strconv.Atoi(strings.TrimSpace(rangeParts[0]))
				end, err2 := strconv.Atoi(strings.TrimSpace(rangeParts[1]))
				if err1 != nil || err2 != nil {
					continue
				}
				ranges = append(ranges, pdbRange{
					ID:         ref.ID,
					Start:      start,
					End:        end,
					Method:     method,
					Resolution: resolution,
				})
			}
		}
	}
	return ranges
}

func featureRange(location uniProtLocation) (int, int) {
	if location.Position != nil {
		return location.Position.Value, location.Position.Value
	}
	if location.Start != nil && location.End != nil {
		return location.Start.Value, location.End.Value
	}
	return 0, 0
}

func computeDisorderedRegions(plddt []float64, length int) []bool {
	if len(plddt) == 0 || length == 0 {
		return make([]bool, length)
	}
	disorder := make([]bool, length)
	for i := 0; i < length && i < len(plddt); i++ {
		if plddt[i] < 50 {
			disorder[i] = true
		}
	}
	return disorder
}

func compressDisorder(disorder []bool) []rangeInfo {
	var regions []rangeInfo
	start := 0
	for i, flag := range disorder {
		if flag && start == 0 {
			start = i + 1
		}
		if !flag && start != 0 {
			regions = append(regions, rangeInfo{Start: start, End: i, Type: "disorder", Source: "pLDDT"})
			start = 0
		}
	}
	if start != 0 {
		regions = append(regions, rangeInfo{Start: start, End: len(disorder), Type: "disorder", Source: "pLDDT"})
	}
	return regions
}

func parseRegion(region string) (*rangeInfo, string, error) {
	if region == "" {
		return nil, "", nil
	}
	rangePattern := regexp.MustCompile(`^\s*(\d+)\s*-\s*(\d+)\s*$`)
	if rangePattern.MatchString(region) {
		matches := rangePattern.FindStringSubmatch(region)
		start, _ := strconv.Atoi(matches[1])
		end, _ := strconv.Atoi(matches[2])
		if start <= 0 || end <= 0 || start > end {
			return nil, "", errors.New("region range must be start-end with start <= end")
		}
		return &rangeInfo{Start: start, End: end, Type: "user_region", Source: "user"}, "", nil
	}
	return nil, strings.TrimSpace(region), nil
}

func buildCandidates(sequence string, regionRange *rangeInfo, regionName string, domains []rangeInfo, pdbRanges []pdbRange, disordered []bool, minLength, maxLength int) []candidate {
	var candidates []candidate
	seen := map[string]bool{}
	addCandidate := func(start, end int, source, name, pdbID string) {
		if start <= 0 || end <= 0 || start > end {
			return
		}
		length := end - start + 1
		if length < minLength {
			return
		}
		if maxLength > 0 && length > maxLength {
			return
		}
		key := fmt.Sprintf("%d-%d", start, end)
		if seen[key] {
			return
		}
		seen[key] = true
		candidates = append(candidates, candidate{
			Start:  start,
			End:    end,
			Source: source,
			Name:   name,
			PDBID:  pdbID,
		})
	}

	if regionRange != nil {
		addCandidate(regionRange.Start, regionRange.End, "user", "user_region", "")
	}

	for _, domain := range domains {
		if regionName != "" && !strings.Contains(strings.ToLower(domain.Name), strings.ToLower(regionName)) {
			continue
		}
		addCandidate(domain.Start, domain.End, "domain", domain.Name, "")
	}

	for _, pdb := range pdbRanges {
		addCandidate(pdb.Start, pdb.End, "pdb", pdb.ID, pdb.ID)
	}

	if regionRange == nil && regionName == "" {
		orderedSegments := orderedRanges(disordered)
		for _, seg := range orderedSegments {
			addCandidate(seg.Start, seg.End, "ordered", "ordered_segment", "")
		}
	}

	return candidates
}

func orderedRanges(disordered []bool) []rangeInfo {
	var ranges []rangeInfo
	start := 0
	for i, flag := range disordered {
		if !flag && start == 0 {
			start = i + 1
		}
		if flag && start != 0 {
			ranges = append(ranges, rangeInfo{Start: start, End: i, Type: "ordered", Source: "pLDDT"})
			start = 0
		}
	}
	if start != 0 {
		ranges = append(ranges, rangeInfo{Start: start, End: len(disordered), Type: "ordered", Source: "pLDDT"})
	}
	return ranges
}

func scoreCandidates(candidates []candidate, ctx boundaryContext, minLength, maxLength int) []candidate {
	for i := range candidates {
		startScore, startRationale := boundaryScore(candidates[i].Start, "start", ctx)
		endScore, endRationale := boundaryScore(candidates[i].End, "end", ctx)
		avgScore := (startScore + endScore) / 2
		candidates[i].Score = avgScore
		candidates[i].Rationale = append(startRationale, endRationale...)
		if candidates[i].Name != "" && candidates[i].Source == "domain" {
			candidates[i].Evidence.Domain = candidates[i].Name
		}
		if candidates[i].PDBID != "" {
			candidates[i].Evidence.PDBMatch = candidates[i].PDBID
		}
	}
	sort.SliceStable(candidates, func(i, j int) bool {
		return candidates[i].Score > candidates[j].Score
	})
	return candidates
}

func boundaryScore(pos int, side string, ctx boundaryContext) (float64, []string) {
	score := 0.0
	var rationale []string

	if isDisorderTransition(pos, side, ctx.Disorder) {
		score += 30
		rationale = append(rationale, "disorder transition")
	}
	if isDomainBoundary(pos, ctx.DomainRanges) {
		score += 25
		rationale = append(rationale, "domain boundary")
	}
	if isLoopRegion(pos, ctx.PLDDT) {
		score += 20
		rationale = append(rationale, "loop-like region")
	}
	if hasStructuredSide(pos, side, ctx.PLDDT) {
		score += 15
		rationale = append(rationale, "high pLDDT side")
	}
	if matchesPDBBoundary(pos, ctx.PDBRanges) {
		score += 10
		rationale = append(rationale, "PDB boundary")
	}

	if withinRanges(pos, ctx.HelixRanges) || withinRanges(pos, ctx.StrandRanges) {
		score -= 50
		rationale = append(rationale, "cuts secondary structure")
	}
	if withinRanges(pos, ctx.ActiveSites) {
		score -= 100
		rationale = append(rationale, "near active site")
	}
	if withinPositions(pos, ctx.PTMPositions, 5) {
		score -= 20
		rationale = append(rationale, "near PTM site")
	}

	return clamp(score, 0, 100), rationale
}

func isDisorderTransition(pos int, side string, disorder []bool) bool {
	if len(disorder) == 0 || pos <= 0 || pos > len(disorder) {
		return false
	}
	idx := pos - 1
	if side == "start" {
		if disorder[idx] {
			return false
		}
		if idx == 0 {
			return true
		}
		return disorder[idx-1]
	}
	if disorder[idx] {
		return false
	}
	if idx == len(disorder)-1 {
		return true
	}
	return disorder[idx+1]
}

func isDomainBoundary(pos int, domains []rangeInfo) bool {
	for _, domain := range domains {
		if abs(pos-domain.Start) <= 3 || abs(pos-domain.End) <= 3 {
			return true
		}
	}
	return false
}

func matchesPDBBoundary(pos int, pdbRanges []pdbRange) bool {
	for _, pdb := range pdbRanges {
		if abs(pos-pdb.Start) <= 3 || abs(pos-pdb.End) <= 3 {
			return true
		}
	}
	return false
}

func isLoopRegion(pos int, plddt []float64) bool {
	if len(plddt) == 0 || pos <= 2 || pos >= len(plddt)-2 {
		return false
	}
	center := avgWindow(plddt, pos-2, pos+2)
	left := avgWindow(plddt, max(0, pos-8), pos-3)
	right := avgWindow(plddt, pos+3, min(len(plddt)-1, pos+8))
	return center < 70 && left > 70 && right > 70
}

func hasStructuredSide(pos int, side string, plddt []float64) bool {
	if len(plddt) == 0 {
		return false
	}
	if side == "start" {
		return avgWindow(plddt, pos-1, min(len(plddt)-1, pos+8)) > 70
	}
	return avgWindow(plddt, max(0, pos-10), pos-1) > 70
}

func withinRanges(pos int, ranges []rangeInfo) bool {
	for _, r := range ranges {
		if pos >= r.Start && pos <= r.End {
			return true
		}
	}
	return false
}

func withinPositions(pos int, positions []int, buffer int) bool {
	for _, p := range positions {
		if abs(pos-p) <= buffer {
			return true
		}
	}
	return false
}

func buildPredictions(candidates []candidate, plddt []float64) []prediction {
	var preds []prediction
	for i, cand := range candidates {
		pred := prediction{
			Rank:      i + 1,
			Start:     cand.Start,
			End:       cand.End,
			Length:    cand.Length(),
			Score:     math.Round(cand.Score),
			Rationale: strings.Join(uniqueStrings(cand.Rationale), ", "),
			Evidence:  cand.Evidence,
		}
		if len(plddt) > 0 {
			avg, fraction := plddtStats(plddt, cand.Start, cand.End)
			pred.Evidence.AvgPLDDT = avg
			pred.Evidence.DisorderFraction = fraction
		}
		preds = append(preds, pred)
	}
	return preds
}

func (c candidate) Length() int {
	return c.End - c.Start + 1
}

func plddtStats(plddt []float64, start, end int) (float64, float64) {
	startIdx := max(0, start-1)
	endIdx := min(len(plddt)-1, end-1)
	var sum float64
	var disorder int
	count := 0
	for i := startIdx; i <= endIdx; i++ {
		sum += plddt[i]
		if plddt[i] < 50 {
			disorder++
		}
		count++
	}
	if count == 0 {
		return 0, 0
	}
	return math.Round(sum/float64(count)*10) / 10, math.Round(float64(disorder)/float64(count)*100) / 100
}

func printSummary(name, accession string, length int, candidates []candidate, disordered []rangeInfo, pdbRanges []pdbRange, warnings []string) {
	title := fmt.Sprintf("CONSTRUCT BOUNDARY PREDICTIONS FOR %s (%d aa)", name, length)
	fmt.Println(title)
	fmt.Println(strings.Repeat("=", len(title)))
	fmt.Println()
	fmt.Printf("%-4s  %-12s  %-7s  %-5s  %s\n", "Rank", "Region", "Length", "Score", "Rationale")
	fmt.Printf("%-4s  %-12s  %-7s  %-5s  %s\n", "----", "------------", "------", "-----", "---------------------------------")
	for i, cand := range candidates {
		rationale := strings.Join(uniqueStrings(cand.Rationale), "; ")
		fmt.Printf("%-4d  %-12s  %-7d  %-5.0f  %s\n", i+1, fmt.Sprintf("%d-%d", cand.Start, cand.End), cand.Length(), cand.Score, rationale)
	}

	if len(disordered) > 0 {
		fmt.Println()
		fmt.Println("DISORDERED REGIONS (pLDDT < 50):")
		for _, region := range disordered {
			fmt.Printf("  %d-%d\n", region.Start, region.End)
		}
	}

	if len(pdbRanges) > 0 {
		fmt.Println()
		fmt.Println("EXISTING PDB STRUCTURES:")
		for _, pdb := range pdbRanges {
			label := fmt.Sprintf("%s: %d-%d", pdb.ID, pdb.Start, pdb.End)
			if pdb.Resolution != "" {
				label = fmt.Sprintf("%s (%s Å)", label, pdb.Resolution)
			}
			fmt.Printf("  %s\n", label)
		}
	}

	if len(warnings) > 0 {
		fmt.Println()
		fmt.Println("WARNINGS:")
		for _, warning := range warnings {
			fmt.Printf("  - %s\n", warning)
		}
	}
}

func buildASCIIVisualization(length int, plddt []float64, disordered []bool, domains []rangeInfo, candidates []candidate) string {
	width := 80
	if length < width {
		width = length
	}
	scale := float64(length) / float64(width)
	var buf bytes.Buffer

	buf.WriteString("Position: ")
	for i := 0; i < width; i++ {
		if i%20 == 0 {
			buf.WriteString("|")
		} else {
			buf.WriteString("-")
		}
	}
	buf.WriteString("\n")

	buf.WriteString("pLDDT:    ")
	for i := 0; i < width; i++ {
		start := int(float64(i) * scale)
		end := int(float64(i+1)*scale) - 1
		if end < start {
			end = start
		}
		char := plddtChar(avgWindow(plddt, start, end))
		buf.WriteString(char)
	}
	buf.WriteString("\n")

	buf.WriteString("Disorder: ")
	for i := 0; i < width; i++ {
		start := int(float64(i) * scale)
		end := int(float64(i+1)*scale) - 1
		if end < start {
			end = start
		}
		if sliceAny(disordered, start, end) {
			buf.WriteString("#")
		} else {
			buf.WriteString(".")
		}
	}
	buf.WriteString("\n")

	buf.WriteString("Domains:  ")
	domainLine := make([]rune, width)
	for i := range domainLine {
		domainLine[i] = ' '
	}
	for _, domain := range domains {
		start := int(float64(domain.Start-1) / scale)
		end := int(float64(domain.End-1) / scale)
		if start < 0 {
			start = 0
		}
		if end >= width {
			end = width - 1
		}
		for i := start; i <= end; i++ {
			domainLine[i] = '='
		}
	}
	buf.WriteString(string(domainLine))
	buf.WriteString("\n")

	buf.WriteString("Suggested:")
	suggestLine := make([]rune, width)
	for i := range suggestLine {
		suggestLine[i] = ' '
	}
	for i, cand := range candidates {
		if i >= 3 {
			break
		}
		start := int(float64(cand.Start-1) / scale)
		end := int(float64(cand.End-1) / scale)
		if start < 0 {
			start = 0
		}
		if end >= width {
			end = width - 1
		}
		for j := start; j <= end; j++ {
			suggestLine[j] = rune('1' + i)
		}
	}
	buf.WriteString(string(suggestLine))
	return buf.String()
}

func plddtChar(avg float64) string {
	chars := []string{" ", ".", ":", "-", "=", "+", "*", "#"}
	if avg == 0 {
		return " "
	}
	idx := int(avg / 100 * float64(len(chars)-1))
	if idx < 0 {
		idx = 0
	}
	if idx >= len(chars) {
		idx = len(chars) - 1
	}
	return chars[idx]
}

func sliceAny(flags []bool, start, end int) bool {
	if len(flags) == 0 {
		return false
	}
	start = max(0, start)
	end = min(len(flags)-1, end)
	for i := start; i <= end; i++ {
		if flags[i] {
			return true
		}
	}
	return false
}

func avgWindow(values []float64, start, end int) float64 {
	if len(values) == 0 || start > end {
		return 0
	}
	start = max(0, start)
	end = min(len(values)-1, end)
	if start > end {
		return 0
	}
	sum := 0.0
	count := 0
	for i := start; i <= end; i++ {
		sum += values[i]
		count++
	}
	if count == 0 {
		return 0
	}
	return sum / float64(count)
}

func uniqueStrings(items []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, item := range items {
		item = strings.TrimSpace(item)
		if item == "" || seen[item] {
			continue
		}
		seen[item] = true
		out = append(out, item)
	}
	return out
}

func firstGene(genes []geneInfo) string {
	if len(genes) == 0 {
		return ""
	}
	return genes[0].GeneName.Value
}

func writeJSON(w io.Writer, payload interface{}) error {
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	return enc.Encode(payload)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func abs(value int) int {
	if value < 0 {
		return -value
	}
	return value
}

func clamp(value, minValue, maxValue float64) float64 {
	if value < minValue {
		return minValue
	}
	if value > maxValue {
		return maxValue
	}
	return value
}

func fatalf(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}
