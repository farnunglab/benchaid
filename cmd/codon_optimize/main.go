package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

const (
	idtAuthURL  = "https://www.idtdna.com/Identityserver/connect/token"
	idtCodonURL = "https://www.idtdna.com/restapi/v1/CodonOpt/Optimize"
)

var organismMap = map[string]string{
	"insect":    "Spodoptera frugiperda",
	"sf9":       "Spodoptera frugiperda",
	"sf21":      "Spodoptera frugiperda",
	"hi5":       "Trichoplusia ni",
	"ecoli":     "Escherichia coli",
	"e.coli":    "Escherichia coli",
	"bacteria":  "Escherichia coli",
	"human":     "Homo sapiens (human)",
	"mammalian": "Homo sapiens (human)",
	"hek":       "Homo sapiens (human)",
	"cho":       "Cricetulus griseus (hamster)",
}

var vectorOrganism = map[string]string{
	"438":  "insect",
	"1-":   "ecoli",
	"pvex": "human",
}

type seqInfo struct {
	Accession string
	Name      string
	Sequence  string
	Length    int
}

type outputData struct {
	Name              string        `json:"name"`
	Organism          string        `json:"organism"`
	InputProtein      string        `json:"input_protein"`
	InputLengthAA     int           `json:"input_length_aa"`
	OptimizedDNA      string        `json:"optimized_dna"`
	OptimizedLength   int           `json:"optimized_length_bp"`
	GCContent         float64       `json:"gc_content"`
	CAI               interface{}   `json:"cai"`
	ComplexityScores  []interface{} `json:"complexity_scores"`
	ComplexitySummary string        `json:"complexity_summary"`
}

func main() {
	var (
		sequence  string
		accession string
		residues  string
		name      string
		organism  string
		vector    string
		output    string
		jsonOut   bool
		fastaOut  bool
	)

	flag.StringVar(&sequence, "sequence", "", "Protein or DNA sequence")
	flag.StringVar(&sequence, "s", "", "Protein or DNA sequence")
	flag.StringVar(&accession, "accession", "", "NCBI protein accession (NP_, XP_, etc.)")
	flag.StringVar(&accession, "a", "", "NCBI protein accession (NP_, XP_, etc.)")
	flag.StringVar(&residues, "residues", "", "Residue range to extract (e.g., 1-300)")
	flag.StringVar(&residues, "r", "", "Residue range to extract (e.g., 1-300)")
	flag.StringVar(&name, "name", "", "Gene/construct name")
	flag.StringVar(&name, "n", "", "Gene/construct name")
	flag.StringVar(&organism, "organism", "", "Target organism for optimization")
	flag.StringVar(&organism, "o", "", "Target organism for optimization")
	flag.StringVar(&vector, "vector", "", "Target vector (infers organism)")
	flag.StringVar(&vector, "v", "", "Target vector (infers organism)")
	flag.StringVar(&output, "output", "", "Output file (default: stdout)")
	flag.StringVar(&output, "O", "", "Output file (default: stdout)")
	flag.BoolVar(&jsonOut, "json", false, "Output as JSON")
	flag.BoolVar(&fastaOut, "fasta", false, "Output as FASTA")
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Codon optimize sequences using IDT API\n\n")
		fmt.Fprintf(os.Stderr, "Usage:\n")
		fmt.Fprintf(os.Stderr, "  %s --sequence MKTLLLTLVVV... --organism insect\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s --accession NP_001234567 --organism ecoli\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s --accession NP_001234567 --residues 1-300 --organism human\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s --accession NP_001234567 --vector 438-C\n\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "Organisms:\n")
		fmt.Fprintf(os.Stderr, "  insect, sf9, sf21, hi5    -> Spodoptera frugiperda / Trichoplusia ni\n")
		fmt.Fprintf(os.Stderr, "  ecoli, bacteria           -> Escherichia coli\n")
		fmt.Fprintf(os.Stderr, "  human, mammalian, hek     -> Homo sapiens\n")
		fmt.Fprintf(os.Stderr, "  cho                       -> Cricetulus griseus\n\n")
		fmt.Fprintf(os.Stderr, "Vector inference:\n")
		fmt.Fprintf(os.Stderr, "  438-*   -> insect\n")
		fmt.Fprintf(os.Stderr, "  1-*     -> ecoli\n")
		fmt.Fprintf(os.Stderr, "  pVEX-*  -> human\n\n")
		flag.PrintDefaults()
	}
	flag.Parse()

	if sequence == "" && accession == "" {
		fatalf("either --sequence or --accession is required")
	}
	if sequence != "" && accession != "" {
		fatalf("choose only one of --sequence or --accession")
	}
	if organism == "" && vector == "" {
		fatalf("either --organism or --vector is required")
	}
	if organism != "" && vector != "" {
		fatalf("choose only one of --organism or --vector")
	}

	loadEnvFromFile(".env")

	clientID := os.Getenv("IDT_CLIENT_ID")
	clientSecret := os.Getenv("IDT_CLIENT_SECRET")
	username := os.Getenv("IDT_USERNAME")
	password := os.Getenv("IDT_PASSWORD")
	if clientID == "" || clientSecret == "" || username == "" || password == "" {
		fatalf("IDT credentials must be set (IDT_CLIENT_ID, IDT_CLIENT_SECRET, IDT_USERNAME, IDT_PASSWORD)")
	}

	var seq string
	var seqName string
	if accession != "" {
		fmt.Fprintf(os.Stderr, "Fetching %s from NCBI...\n", accession)
		info, err := fetchProteinSequence(accession)
		if err != nil {
			fatalf("failed to fetch sequence: %v", err)
		}
		seq = info.Sequence
		if name != "" {
			seqName = name
		} else {
			seqName = info.Name
		}
	} else {
		seq = normalizeSequence(sequence)
		if name != "" {
			seqName = name
		} else {
			seqName = "Query"
		}
	}

	if residues != "" {
		origLen := len(seq)
		fragment, err := extractResidues(seq, residues)
		if err != nil {
			fatalf("%v", err)
		}
		seq = fragment
		fmt.Fprintf(os.Stderr, "Extracted residues %s: %d -> %d aa\n", residues, origLen, len(seq))
		seqName = fmt.Sprintf("%s_%s", seqName, strings.ReplaceAll(residues, "-", "_"))
	}

	if vector != "" {
		inf, ok := inferOrganismFromVector(vector)
		if !ok {
			fatalf("could not infer organism from vector: %s", vector)
		}
		fmt.Fprintf(os.Stderr, "Inferred organism from %s: %s\n", vector, inf)
		organism = inf
	}

	organismName := normalizeOrganism(organism)
	fmt.Fprintf(os.Stderr, "Authenticating with IDT...\n")
	token, err := getIDTToken(clientID, clientSecret, username, password)
	if err != nil {
		fatalf("failed to authenticate with IDT: %v", err)
	}

	fmt.Fprintf(os.Stderr, "Optimizing %d aa for %s...\n", len(seq), organismName)
	sequenceType := inferSequenceType(seq)
	result, err := optimizeCodonIDT(seqName, seq, organismName, sequenceType, "gene", token)
	if err != nil {
		fatalf("codon optimization failed: %v", err)
	}

	optimized := result.OptResult.FullSequence
	if optimized == "" {
		fatalf("IDT response missing optimized sequence")
	}

	out := outputData{
		Name:              seqName,
		Organism:          organismName,
		InputProtein:      seq,
		InputLengthAA:     len(seq),
		OptimizedDNA:      optimized,
		OptimizedLength:   len(optimized),
		GCContent:         gcContent(optimized),
		CAI:               nil,
		ComplexityScores:  toComplexityMessages(result.OptResult.Complexities),
		ComplexitySummary: result.OptResult.ComplexitySummary,
	}

	var outputText string
	switch {
	case jsonOut:
		encoded, err := json.MarshalIndent(out, "", "  ")
		if err != nil {
			fatalf("failed to encode JSON: %v", err)
		}
		outputText = string(encoded)
	case fastaOut:
		outputText = fmt.Sprintf(">%s_codon_optimized_%s\n%s", seqName, organism, optimized)
	default:
		outputText = fmt.Sprintf(
			"Codon Optimization Result\n=========================\nName:           %s\nOrganism:       %s\nInput:          %d aa\nOutput:         %d bp\nGC Content:     %.2f\nCAI:            %v\nComplexity:     %s\n\nOptimized DNA Sequence:\n%s\n",
			seqName, organismName, len(seq), len(optimized), out.GCContent, out.CAI, out.ComplexitySummary, optimized,
		)
	}

	if output != "" {
		if err := os.WriteFile(output, []byte(outputText), 0o644); err != nil {
			fatalf("failed to write output: %v", err)
		}
		fmt.Fprintf(os.Stderr, "Written to %s\n", output)
	} else {
		fmt.Println(outputText)
	}
}

func loadEnvFromFile(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, val, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		val = strings.TrimSpace(val)
		val = strings.Trim(val, `"'`)
		if key != "" && val != "" && os.Getenv(key) == "" {
			_ = os.Setenv(key, val)
		}
	}
}

func normalizeSequence(seq string) string {
	replacer := strings.NewReplacer(" ", "", "\n", "", "\r", "", "\t", "")
	return strings.ToUpper(replacer.Replace(seq))
}

func normalizeOrganism(org string) string {
	orgLower := strings.ToLower(org)
	if mapped, ok := organismMap[orgLower]; ok {
		return mapped
	}
	return org
}

func inferOrganismFromVector(vector string) (string, bool) {
	lower := strings.ToLower(vector)
	for prefix, org := range vectorOrganism {
		if strings.Contains(lower, prefix) {
			return org, true
		}
	}
	return "", false
}

func extractResidues(sequence, residueRange string) (string, error) {
	parts := strings.Split(strings.ReplaceAll(residueRange, " ", ""), "-")
	if len(parts) != 2 {
		return sequence, fmt.Errorf("invalid residue range: %s", residueRange)
	}
	start, err := parsePositiveInt(parts[0])
	if err != nil {
		return sequence, fmt.Errorf("invalid residue range: %s", residueRange)
	}
	end, err := parsePositiveInt(parts[1])
	if err != nil {
		return sequence, fmt.Errorf("invalid residue range: %s", residueRange)
	}
	if start < 1 || end < start || end > len(sequence) {
		return sequence, fmt.Errorf("invalid residue range: %s", residueRange)
	}
	return sequence[start-1 : end], nil
}

func parsePositiveInt(val string) (int, error) {
	n := 0
	for _, r := range val {
		if r < '0' || r > '9' {
			return 0, errors.New("not a number")
		}
		n = n*10 + int(r-'0')
	}
	if n <= 0 {
		return 0, errors.New("not positive")
	}
	return n, nil
}

func fetchProteinSequence(accession string) (seqInfo, error) {
	query := url.QueryEscape(accession)
	reqURL := fmt.Sprintf("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=protein&id=%s&rettype=fasta&retmode=text", query)
	req, err := http.NewRequest(http.MethodGet, reqURL, nil)
	if err != nil {
		return seqInfo{}, err
	}
	req.Header.Set("User-Agent", "Benchmate/1.0")
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return seqInfo{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return seqInfo{}, fmt.Errorf("NCBI fetch error: %s", strings.TrimSpace(string(body)))
	}
	fasta, err := io.ReadAll(resp.Body)
	if err != nil {
		return seqInfo{}, err
	}
	lines := strings.Split(strings.TrimSpace(string(fasta)), "\n")
	if len(lines) == 0 {
		return seqInfo{}, fmt.Errorf("empty FASTA response")
	}
	header := lines[0]
	sequence := normalizeSequence(strings.Join(lines[1:], ""))
	name := accession
	if strings.Contains(header, "[") {
		parts := strings.Fields(header)
		for _, part := range parts {
			if strings.HasPrefix(part, ">") || strings.HasPrefix(part, "[") {
				continue
			}
			name = part
			break
		}
	}
	return seqInfo{
		Accession: accession,
		Name:      name,
		Sequence:  sequence,
		Length:    len(sequence),
	}, nil
}

func getIDTToken(clientID, clientSecret, username, password string) (string, error) {
	data := url.Values{}
	data.Set("grant_type", "password")
	data.Set("scope", "test")
	data.Set("username", username)
	data.Set("password", password)
	encoded := data.Encode()

	creds := base64.StdEncoding.EncodeToString([]byte(clientID + ":" + clientSecret))
	req, err := http.NewRequest(http.MethodPost, idtAuthURL, strings.NewReader(encoded))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Authorization", "Basic "+creds)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("IDT auth error: %s", strings.TrimSpace(string(body)))
	}
	var payload map[string]interface{}
	if err := json.Unmarshal(body, &payload); err != nil {
		return "", err
	}
	token, _ := payload["access_token"].(string)
	if token == "" {
		return "", errors.New("missing access_token")
	}
	return token, nil
}

type complexityItem struct {
	Text string `json:"Text"`
}

type codonOptResponse struct {
	Name      string `json:"Name"`
	OptResult struct {
		FullSequence              string           `json:"FullSequence"`
		ComplexityScore           float64          `json:"ComplexityScore"`
		ComplexitySummary         string           `json:"ComplexitySummary"`
		Complexities              []complexityItem `json:"Complexities"`
		ComplexityScreenerResults []interface{}    `json:"ComplexityScreenerResults"`
	} `json:"OptResult"`
}

func optimizeCodonIDT(name, sequence, organismName, sequenceType, productType, token string) (codonOptResponse, error) {
	payload := map[string]interface{}{
		"organism": organismName,
		"optimizationItems": []map[string]string{
			{
				"Name":     name,
				"Sequence": sequence,
			},
		},
		"sequenceType": sequenceType,
		"productType":  productType,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return codonOptResponse{}, err
	}
	req, err := http.NewRequest(http.MethodPost, idtCodonURL, bytes.NewReader(body))
	if err != nil {
		return codonOptResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return codonOptResponse{}, err
	}
	defer resp.Body.Close()
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return codonOptResponse{}, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return codonOptResponse{}, fmt.Errorf("IDT API error: %s", strings.TrimSpace(string(respBody)))
	}
	var results []codonOptResponse
	if err := json.Unmarshal(respBody, &results); err != nil {
		return codonOptResponse{}, err
	}
	if len(results) == 0 {
		return codonOptResponse{}, errors.New("empty IDT response")
	}
	return results[0], nil
}

func inferSequenceType(seq string) string {
	seq = strings.ToUpper(seq)
	for _, r := range seq {
		switch r {
		case 'A', 'C', 'G', 'T', 'U', 'N':
			continue
		default:
			return "aminoAcid"
		}
	}
	return "dna"
}

func gcContent(seq string) float64 {
	if seq == "" {
		return 0
	}
	seq = strings.ToUpper(seq)
	gc := 0
	for _, r := range seq {
		if r == 'G' || r == 'C' {
			gc++
		}
	}
	return (float64(gc) / float64(len(seq))) * 100
}

func toComplexityMessages(items []complexityItem) []interface{} {
	if len(items) == 0 {
		return nil
	}
	out := make([]interface{}, 0, len(items))
	for _, item := range items {
		if strings.TrimSpace(item.Text) == "" {
			continue
		}
		out = append(out, item.Text)
	}
	return out
}

func fatalf(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}
