package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	licv1FwdOverhang = "TACTTCCAATCCAATGCA"
	licv1RevOverhang = "TTATCCACTTCCAATGTTATTA"
)

type Vector struct {
	Name               string
	Aliases            []string
	Description        string
	Sequence           string
	SequenceFile       string
	Length             int
	CloningMethod      string
	InsertionSite      int
	FivePrimeJunction  string
	ThreePrimeJunction string
	RestrictionSites   []string
	Features           []Feature
	NTerminalTag       string
	CTerminalTag       string
	ReadingFrame       int
	SourcePath         string
}

type Feature struct {
	Name       string
	Type       string
	Start      int
	End        int
	Strand     string
	Qualifiers map[string]string
	Location   string
}

type Construct struct {
	Name            string
	Description     string
	Sequence        string
	Length          int
	Vector          string
	InsertName      string
	InsertSource    string
	InsertRange     string
	CloningMethod   string
	Features        []Feature
	ExpectedProtein string
	InsertProtein   string
	InsertDNA       string
	CreatedDate     string
	PrimerPair      []string
}

type ValidationResult struct {
	Valid             bool
	Warnings          []string
	Errors            []string
	FusionProtein     string
	FusionLengthAA    int
	ConstructLengthBP int
}

type seqInfo struct {
	Name    string
	DNA     string
	Protein string
	Source  string
	Range   string
}

type restrictionSite struct {
	Name     string
	Sequence string
	CutIndex int
}

var restrictionSites = map[string]restrictionSite{
	"NdeI":  {Name: "NdeI", Sequence: "CATATG", CutIndex: 2},
	"XhoI":  {Name: "XhoI", Sequence: "CTCGAG", CutIndex: 1},
	"BamHI": {Name: "BamHI", Sequence: "GGATCC", CutIndex: 1},
	"EcoRI": {Name: "EcoRI", Sequence: "GAATTC", CutIndex: 1},
}

func main() {
	var (
		vectorName      string
		insertAccession string
		insertFile      string
		insertSeq       string
		insertName      string
		residues        string
		method          string
		output          string
		listVectors     bool
		vectorInfo      string
		jsonOut         bool
	)

	flag.StringVar(&vectorName, "vector", "", "Vector name from library")
	flag.StringVar(&insertAccession, "insert-accession", "", "NCBI accession for insert (NM_, NP_, XP_)")
	flag.StringVar(&insertFile, "insert-file", "", "Insert sequence file (FASTA/GenBank)")
	flag.StringVar(&insertSeq, "insert-sequence", "", "Insert DNA sequence")
	flag.StringVar(&insertName, "insert-name", "", "Insert name")
	flag.StringVar(&residues, "residues", "", "Residue range (e.g. 1-500)")
	flag.StringVar(&method, "method", "", "Cloning method (lic, gibson, restriction)")
	flag.StringVar(&output, "output", "", "Output GenBank file path (.gb or .gbk)")
	flag.BoolVar(&listVectors, "list-vectors", false, "List available vectors")
	flag.StringVar(&vectorInfo, "vector-info", "", "Show details for a vector")
	flag.BoolVar(&jsonOut, "json", false, "Write construct metadata as JSON (alongside GenBank)")
	flag.Parse()

	vectors, err := loadVectors()
	if err != nil {
		fatalf("failed to load vectors: %v", err)
	}

	if listVectors {
		printVectorList(vectors)
		return
	}

	if vectorInfo != "" {
		vector, ok := findVector(vectorInfo, vectors)
		if !ok {
			fatalf("vector %q not found", vectorInfo)
		}
		printVectorInfo(vector)
		return
	}

	if vectorName == "" {
		fatalf("provide --vector")
	}
	if output == "" {
		fatalf("provide --output")
	}

	vector, ok := findVector(vectorName, vectors)
	if !ok {
		fatalf("vector %q not found; use --list-vectors", vectorName)
	}
	if vector.Sequence == "" {
		fatalf("vector %q has no sequence; supply a vector definition with sequence or sequence_file", vector.Name)
	}

	insert, err := loadInsert(seqInfo{
		Name:   insertName,
		DNA:    insertSeq,
		Source: insertAccession,
		Range:  residues,
	}, insertFile, insertAccession)
	if err != nil {
		fatalf("failed to load insert: %v", err)
	}

	if insert.Name == "" {
		insert.Name = "Insert"
	}

	if method == "" {
		method = vector.CloningMethod
	}
	if method == "" {
		method = "lic"
	}

	construct, validation, err := buildConstruct(vector, insert, method)
	if err != nil {
		fatalf("failed to build construct: %v", err)
	}

	if len(validation.Errors) > 0 {
		for _, errMsg := range validation.Errors {
			fmt.Fprintf(os.Stderr, "error: %s\n", errMsg)
		}
		os.Exit(1)
	}
	for _, warn := range validation.Warnings {
		fmt.Fprintf(os.Stderr, "warning: %s\n", warn)
	}

	if err := writeGenBank(construct, output); err != nil {
		fatalf("failed to write GenBank: %v", err)
	}
	fmt.Fprintf(os.Stderr, "Written: %s\n", output)

	if jsonOut {
		jsonPath := output + ".json"
		if err := writeJSON(construct, jsonPath); err != nil {
			fatalf("failed to write JSON: %v", err)
		}
		fmt.Fprintf(os.Stderr, "Written: %s\n", jsonPath)
	}
}

func usage() {
	fmt.Fprintf(os.Stderr, "Construct generator\n\n")
	fmt.Fprintf(os.Stderr, "Usage:\n")
	fmt.Fprintf(os.Stderr, "  construct_generator --vector 438-C --insert-accession NM_003170 --residues 1-500 --output spt6.gb\n")
	fmt.Fprintf(os.Stderr, "  construct_generator --vector pET28a --insert-file gene.fasta --method restriction --output construct.gb\n")
	fmt.Fprintf(os.Stderr, "  construct_generator --list-vectors\n")
	fmt.Fprintf(os.Stderr, "  construct_generator --vector-info 438-C\n")
}

func fatalf(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}

func printVectorList(vectors []Vector) {
	if len(vectors) == 0 {
		fmt.Println("No vectors available.")
		return
	}
	sort.Slice(vectors, func(i, j int) bool { return vectors[i].Name < vectors[j].Name })
	fmt.Println("Available vectors:")
	for _, v := range vectors {
		tag := v.NTerminalTag
		if tag == "" {
			tag = "-"
		}
		method := strings.ToUpper(v.CloningMethod)
		if method == "" {
			method = "UNKNOWN"
		}
		desc := v.Description
		if desc == "" {
			desc = "No description"
		}
		fmt.Printf("  %-8s %-10s %-18s %s\n", v.Name, method, tag, desc)
	}
}

func printVectorInfo(vector Vector) {
	fmt.Printf("Vector: %s\n", vector.Name)
	if len(vector.Aliases) > 0 {
		fmt.Printf("Aliases: %s\n", strings.Join(vector.Aliases, ", "))
	}
	if vector.Description != "" {
		fmt.Printf("Description: %s\n", vector.Description)
	}
	fmt.Printf("Method: %s\n", vector.CloningMethod)
	fmt.Printf("Insertion site: %d\n", vector.InsertionSite)
	if vector.NTerminalTag != "" {
		fmt.Printf("N-terminal tag: %s\n", vector.NTerminalTag)
	}
	if vector.CTerminalTag != "" {
		fmt.Printf("C-terminal tag: %s\n", vector.CTerminalTag)
	}
	if vector.Sequence != "" {
		fmt.Printf("Length: %d bp\n", len(vector.Sequence))
	}
	if vector.SourcePath != "" {
		fmt.Printf("Source: %s\n", vector.SourcePath)
	}
	if len(vector.Features) > 0 {
		fmt.Printf("Features: %d\n", len(vector.Features))
	}
}

func findVector(name string, vectors []Vector) (Vector, bool) {
	needle := strings.ToLower(strings.TrimSpace(name))
	for _, v := range vectors {
		if strings.ToLower(v.Name) == needle {
			return v, true
		}
		for _, alias := range v.Aliases {
			if strings.ToLower(alias) == needle {
				return v, true
			}
		}
	}
	return Vector{}, false
}

func loadVectors() ([]Vector, error) {
	var vectors []Vector
	vectors = append(vectors, builtInVectors()...)

	home, err := os.UserHomeDir()
	if err == nil {
		path := filepath.Join(home, ".benchaid", "vectors.yaml")
		if _, err := os.Stat(path); err == nil {
			loaded, err := loadVectorFile(path)
			if err != nil {
				return nil, err
			}
			vectors = append(vectors, loaded...)
		}
	}

	if entries, err := os.ReadDir("vectors"); err == nil {
		for _, entry := range entries {
			if entry.IsDir() {
				continue
			}
			name := entry.Name()
			if !strings.HasSuffix(name, ".yaml") && !strings.HasSuffix(name, ".yml") {
				continue
			}
			path := filepath.Join("vectors", name)
			loaded, err := loadVectorFile(path)
			if err != nil {
				return nil, err
			}
			vectors = append(vectors, loaded...)
		}
	}

	return dedupeVectors(vectors), nil
}

func loadVectorFile(path string) ([]Vector, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	sections := splitYAMLDocuments(string(content))
	var vectors []Vector
	for _, section := range sections {
		if strings.TrimSpace(section) == "" {
			continue
		}
		vector, err := parseVectorYAML(path, section)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
		vectors = append(vectors, vector)
	}
	return vectors, nil
}

func dedupeVectors(vectors []Vector) []Vector {
	seen := make(map[string]Vector)
	for _, v := range vectors {
		key := strings.ToLower(v.Name)
		if _, ok := seen[key]; ok {
			if seen[key].Sequence == "" && v.Sequence != "" {
				seen[key] = v
			}
			continue
		}
		seen[key] = v
	}
	result := make([]Vector, 0, len(seen))
	for _, v := range seen {
		result = append(result, v)
	}
	return result
}

func builtInVectors() []Vector {
	return []Vector{
		{
			Name:          "438-C",
			Aliases:       []string{"438C", "pFastBac-438C"},
			Description:   "His6-MBP-TEV insect expression",
			CloningMethod: "lic",
			NTerminalTag:  "His6-MBP-TEV",
			ReadingFrame:  0,
		},
		{
			Name:          "438-A",
			Aliases:       []string{"438A", "pFastBac-438A"},
			Description:   "His6-TEV insect expression",
			CloningMethod: "lic",
			NTerminalTag:  "His6-TEV",
			ReadingFrame:  0,
		},
		{
			Name:          "438-B",
			Aliases:       []string{"438B", "pFastBac-438B"},
			Description:   "His6 insect expression",
			CloningMethod: "lic",
			NTerminalTag:  "His6",
			ReadingFrame:  0,
		},
		{
			Name:          "1-C",
			Aliases:       []string{"1C"},
			Description:   "His6-MBP-TEV E. coli expression",
			CloningMethod: "lic",
			NTerminalTag:  "His6-MBP-TEV",
			ReadingFrame:  0,
		},
		{
			Name:          "1-A",
			Aliases:       []string{"1A"},
			Description:   "His6-TEV E. coli expression",
			CloningMethod: "lic",
			NTerminalTag:  "His6-TEV",
			ReadingFrame:  0,
		},
		{
			Name:             "pET28a",
			Aliases:          []string{"pET-28a"},
			Description:      "His6-Thrombin E. coli T7 expression",
			CloningMethod:    "restriction",
			RestrictionSites: []string{"NdeI", "XhoI"},
			NTerminalTag:     "His6-Thrombin",
			CTerminalTag:     "His6",
			ReadingFrame:     0,
		},
		{
			Name:          "pVEX",
			Aliases:       []string{"pVEX-1"},
			Description:   "FLAG mammalian expression",
			CloningMethod: "gibson",
			NTerminalTag:  "FLAG",
			ReadingFrame:  0,
		},
	}
}

func splitYAMLDocuments(content string) []string {
	lines := strings.Split(content, "\n")
	var docs []string
	var current []string
	for _, line := range lines {
		if strings.TrimSpace(line) == "---" {
			docs = append(docs, strings.Join(current, "\n"))
			current = current[:0]
			continue
		}
		current = append(current, line)
	}
	if len(current) > 0 {
		docs = append(docs, strings.Join(current, "\n"))
	}
	return docs
}

func parseVectorYAML(path, content string) (Vector, error) {
	vector := Vector{
		SourcePath: path,
	}
	var currentFeature *Feature
	var mode string
	var multilineKey string
	var multilineIndent int
	var multilineValue []string

	scanner := bufio.NewScanner(strings.NewReader(content))
	lineNum := 0
	for scanner.Scan() {
		lineNum++
		line := scanner.Text()
		if multilineKey != "" {
			indent := leadingSpaces(line)
			if indent <= multilineIndent && strings.TrimSpace(line) != "" {
				setVectorField(&vector, currentFeature, multilineKey, strings.Join(multilineValue, ""), mode)
				multilineKey = ""
				multilineValue = nil
				mode = ""
			} else {
				multilineValue = append(multilineValue, strings.TrimSpace(line))
				continue
			}
		}

		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		if leadingSpaces(line) == 0 {
			mode = ""
			currentFeature = nil
		}

		if strings.HasPrefix(trimmed, "- ") {
			item := strings.TrimSpace(strings.TrimPrefix(trimmed, "- "))
			switch mode {
			case "aliases":
				vector.Aliases = append(vector.Aliases, stripQuotes(item))
			case "restriction_sites":
				vector.RestrictionSites = append(vector.RestrictionSites, stripQuotes(item))
			case "features", "qualifiers":
				feature := Feature{Qualifiers: make(map[string]string)}
				if strings.Contains(item, ":") {
					key, value := splitKeyValue(item)
					setFeatureField(&feature, key, value)
				}
				vector.Features = append(vector.Features, feature)
				currentFeature = &vector.Features[len(vector.Features)-1]
				mode = "features"
			}
			continue
		}

		if !strings.Contains(trimmed, ":") {
			continue
		}
		key, value := splitKeyValue(trimmed)
		switch key {
		case "aliases":
			if value == "" {
				mode = "aliases"
			} else {
				vector.Aliases = parseInlineList(value)
				mode = ""
			}
		case "restriction_sites":
			if value == "" {
				mode = "restriction_sites"
			} else {
				vector.RestrictionSites = parseInlineList(value)
				mode = ""
			}
		case "features":
			mode = "features"
		case "qualifiers":
			mode = "qualifiers"
		case "sequence":
			if value == "|" || value == ">" {
				multilineKey = "sequence"
				multilineIndent = leadingSpaces(line)
				multilineValue = nil
			} else {
				vector.Sequence = normalizeDNA(stripQuotes(value))
			}
		default:
			if currentFeature != nil && mode == "features" && key != "" {
				setFeatureField(currentFeature, key, value)
			} else if currentFeature != nil && mode == "qualifiers" {
				currentFeature.Qualifiers[key] = stripQuotes(value)
			} else {
				if value == "|" || value == ">" {
					multilineKey = key
					multilineIndent = leadingSpaces(line)
					multilineValue = nil
				} else {
					setVectorField(&vector, currentFeature, key, value, mode)
				}
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return vector, err
	}
	if multilineKey != "" {
		setVectorField(&vector, currentFeature, multilineKey, strings.Join(multilineValue, ""), mode)
	}

	if vector.Sequence == "" && vector.SequenceFile != "" {
		seqPath := resolvePath(filepath.Dir(path), vector.SequenceFile)
		name, seq, err := readSequenceFile(seqPath)
		if err != nil {
			return vector, err
		}
		vector.Sequence = seq
		if vector.Name == "" && name != "" {
			vector.Name = name
		}
	}
	if vector.Sequence != "" && vector.Length == 0 {
		vector.Length = len(vector.Sequence)
	}
	return vector, nil
}

func setVectorField(vector *Vector, currentFeature *Feature, key, value, mode string) {
	value = stripQuotes(strings.TrimSpace(value))
	switch key {
	case "name":
		vector.Name = value
	case "description":
		vector.Description = value
	case "cloning_method":
		vector.CloningMethod = strings.ToLower(value)
	case "sequence_file":
		vector.SequenceFile = value
	case "sequence":
		vector.Sequence = normalizeDNA(value)
	case "length":
		vector.Length = parseInt(value)
	case "insertion_site":
		vector.InsertionSite = parseInt(value)
	case "five_prime_junction":
		vector.FivePrimeJunction = normalizeDNA(value)
	case "three_prime_junction":
		vector.ThreePrimeJunction = normalizeDNA(value)
	case "n_terminal_tag":
		vector.NTerminalTag = value
	case "c_terminal_tag":
		vector.CTerminalTag = value
	case "reading_frame":
		vector.ReadingFrame = parseInt(value)
	}
}

func setFeatureField(feature *Feature, key, value string) {
	value = stripQuotes(strings.TrimSpace(value))
	switch key {
	case "name":
		feature.Name = value
	case "type":
		feature.Type = value
	case "start":
		feature.Start = parseInt(value)
	case "end":
		feature.End = parseInt(value)
	case "strand":
		feature.Strand = value
	}
}

func splitKeyValue(line string) (string, string) {
	parts := strings.SplitN(line, ":", 2)
	key := strings.TrimSpace(parts[0])
	if len(parts) == 1 {
		return key, ""
	}
	return key, strings.TrimSpace(parts[1])
}

func parseInlineList(value string) []string {
	value = strings.TrimSpace(value)
	value = strings.TrimPrefix(value, "[")
	value = strings.TrimSuffix(value, "]")
	if value == "" {
		return nil
	}
	parts := strings.Split(value, ",")
	items := make([]string, 0, len(parts))
	for _, part := range parts {
		item := stripQuotes(strings.TrimSpace(part))
		if item != "" {
			items = append(items, item)
		}
	}
	return items
}

func stripQuotes(value string) string {
	value = strings.TrimSpace(value)
	value = strings.Trim(value, `"'`)
	return value
}

func parseInt(value string) int {
	value = strings.TrimSpace(value)
	if value == "" {
		return 0
	}
	num, err := strconv.Atoi(value)
	if err != nil {
		return 0
	}
	return num
}

func leadingSpaces(line string) int {
	count := 0
	for _, ch := range line {
		if ch == ' ' {
			count++
		} else {
			break
		}
	}
	return count
}

func resolvePath(base, rel string) string {
	if filepath.IsAbs(rel) {
		return rel
	}
	return filepath.Join(base, rel)
}

func loadInsert(base seqInfo, insertFile, accession string) (seqInfo, error) {
	if accession != "" {
		return fetchInsertFromNCBI(accession, base.Range)
	}
	if insertFile != "" {
		name, dna, err := readSequenceFile(insertFile)
		if err != nil {
			return seqInfo{}, err
		}
		if base.Name == "" {
			base.Name = name
		}
		base.DNA = dna
		if base.Source == "" {
			base.Source = insertFile
		}
		return finalizeInsert(base)
	}
	if base.DNA != "" {
		base.DNA = normalizeDNA(base.DNA)
		if base.Source == "" {
			base.Source = "raw"
		}
		return finalizeInsert(base)
	}
	return seqInfo{}, errors.New("provide one of --insert-accession, --insert-file, or --insert-sequence")
}

func finalizeInsert(info seqInfo) (seqInfo, error) {
	if info.DNA == "" {
		return info, errors.New("insert sequence is empty")
	}
	info.DNA = normalizeDNA(info.DNA)
	info.Protein = translate(info.DNA)
	if len(info.DNA) > 50000 {
		return info, fmt.Errorf("insert length %d bp exceeds 50kb limit", len(info.DNA))
	}
	if len(info.DNA) > 10000 {
		fmt.Fprintf(os.Stderr, "warning: insert length %d bp exceeds 10kb\n", len(info.DNA))
	}
	return info, nil
}

func fetchInsertFromNCBI(accession, residueRange string) (seqInfo, error) {
	acc := strings.TrimSpace(accession)
	if acc == "" {
		return seqInfo{}, errors.New("empty accession")
	}
	upper := strings.ToUpper(acc)
	switch {
	case strings.HasPrefix(upper, "NM_") || strings.HasPrefix(upper, "XM_") || strings.HasPrefix(upper, "NR_"):
		return fetchNucleotideCDS(acc, residueRange)
	case strings.HasPrefix(upper, "NP_") || strings.HasPrefix(upper, "XP_"):
		return fetchProteinCDS(acc, residueRange)
	default:
		return seqInfo{}, fmt.Errorf("unsupported accession: %s", acc)
	}
}

func fetchNucleotideCDS(accession, residueRange string) (seqInfo, error) {
	content, err := fetchGenBank("nuccore", accession)
	if err != nil {
		return seqInfo{}, err
	}
	name, seq, cdsInfo, err := parseGenBankCDS(content)
	if err != nil {
		return seqInfo{}, err
	}
	info := seqInfo{
		Name:    name,
		DNA:     seq,
		Protein: cdsInfo.Protein,
		Source:  accession,
	}
	if info.Name == "" {
		info.Name = accession
	}
	if residueRange != "" {
		dna, protein, err := applyResidueRange(seq, info.Protein, residueRange)
		if err != nil {
			return seqInfo{}, err
		}
		info.DNA = dna
		info.Protein = protein
		info.Range = residueRange
	}
	return finalizeInsert(info)
}

func fetchProteinCDS(accession, residueRange string) (seqInfo, error) {
	content, err := fetchGenBank("protein", accession)
	if err != nil {
		return seqInfo{}, err
	}
	proteinSeq, codedBy, err := parseProteinCodedBy(content)
	if err != nil {
		return seqInfo{}, err
	}
	if codedBy == "" {
		return seqInfo{}, fmt.Errorf("no coded_by field for protein %s", accession)
	}
	codedAcc, region, complement, err := parseCodedBy(codedBy)
	if err != nil {
		return seqInfo{}, err
	}
	nuccore, err := fetchGenBank("nuccore", codedAcc)
	if err != nil {
		return seqInfo{}, err
	}
	_, fullSeq := parseGenBankSequence(nuccore)
	if fullSeq == "" {
		return seqInfo{}, errors.New("no nucleotide sequence found")
	}
	dna := extractSequenceRegion(fullSeq, region, complement)
	info := seqInfo{
		Name:    accession,
		DNA:     dna,
		Protein: proteinSeq,
		Source:  accession,
	}
	if residueRange != "" {
		dnaRange, proteinRange, err := applyResidueRange(dna, proteinSeq, residueRange)
		if err != nil {
			return seqInfo{}, err
		}
		info.DNA = dnaRange
		info.Protein = proteinRange
		info.Range = residueRange
	}
	return finalizeInsert(info)
}

func fetchGenBank(db, accession string) (string, error) {
	url := fmt.Sprintf("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=%s&id=%s&rettype=gb&retmode=text", db, accession)
	resp, err := http.Get(url) // #nosec G107 -- NCBI is required by spec
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("ncbi fetch failed: %s: %s", resp.Status, strings.TrimSpace(string(body)))
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

type cdsInfo struct {
	DNA     string
	Protein string
}

func parseGenBankCDS(content string) (string, string, cdsInfo, error) {
	name, sequence := parseGenBankSequence(content)
	if sequence == "" {
		return "", "", cdsInfo{}, errors.New("no sequence found in GenBank")
	}
	cdsFeatures := parseCDSFeatures(content)
	if len(cdsFeatures) == 0 {
		return name, sequence, cdsInfo{DNA: sequence, Protein: translate(sequence)}, nil
	}
	cds := cdsFeatures[0]
	dna := extractSequenceRegion(sequence, cds.Segments, cds.Complement)
	protein := cds.Translation
	if protein == "" {
		protein = translate(dna)
	}
	return name, dna, cdsInfo{DNA: dna, Protein: protein}, nil
}

func parseGenBankSequence(content string) (string, string) {
	var name string
	var seqBuilder strings.Builder
	var inOrigin bool
	scanner := bufio.NewScanner(strings.NewReader(content))
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "LOCUS") {
			fields := strings.Fields(line)
			if len(fields) > 1 {
				name = fields[1]
			}
		}
		if strings.HasPrefix(line, "ORIGIN") {
			inOrigin = true
			continue
		}
		if inOrigin {
			if strings.HasPrefix(line, "//") {
				break
			}
			for _, ch := range line {
				if ch >= 'A' && ch <= 'Z' {
					seqBuilder.WriteRune(ch)
				} else if ch >= 'a' && ch <= 'z' {
					seqBuilder.WriteRune(ch - 'a' + 'A')
				}
			}
		}
	}
	return name, seqBuilder.String()
}

type cdsFeature struct {
	Segments    []segment
	Complement  bool
	Translation string
}

type segment struct {
	Start int
	End   int
}

func parseCDSFeatures(content string) []cdsFeature {
	var features []cdsFeature
	scanner := bufio.NewScanner(strings.NewReader(content))
	var current *cdsFeature
	var inFeatures bool
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "FEATURES") {
			inFeatures = true
			continue
		}
		if strings.HasPrefix(line, "ORIGIN") {
			break
		}
		if !inFeatures {
			continue
		}
		if strings.HasPrefix(line, "     CDS") {
			loc := strings.TrimSpace(line[8:])
			segments, complement := parseLocation(loc)
			feature := cdsFeature{Segments: segments, Complement: complement}
			features = append(features, feature)
			current = &features[len(features)-1]
			continue
		}
		if current != nil && strings.Contains(line, "/translation=") {
			translation := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(line), "/translation="))
			translation = strings.Trim(translation, "\"")
			current.Translation = translation
		} else if current != nil && current.Translation != "" && strings.HasPrefix(strings.TrimSpace(line), "\"") {
			current.Translation += strings.Trim(strings.TrimSpace(line), "\"")
		}
	}
	return features
}

func parseProteinCodedBy(content string) (string, string, error) {
	var proteinSeq string
	var codedBy string
	scanner := bufio.NewScanner(strings.NewReader(content))
	var inOrigin bool
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "ORIGIN") {
			inOrigin = true
			continue
		}
		if inOrigin {
			if strings.HasPrefix(line, "//") {
				break
			}
			for _, ch := range line {
				if ch >= 'A' && ch <= 'Z' {
					proteinSeq += string(ch)
				} else if ch >= 'a' && ch <= 'z' {
					proteinSeq += string(ch - 'a' + 'A')
				}
			}
		}
		if strings.Contains(line, "/coded_by=") {
			codedBy = strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(line), "/coded_by="))
			codedBy = strings.Trim(codedBy, "\"")
		} else if codedBy != "" && strings.HasPrefix(strings.TrimSpace(line), "\"") {
			codedBy += strings.Trim(strings.TrimSpace(line), "\"")
		}
	}
	if proteinSeq == "" {
		return "", "", errors.New("no protein sequence found")
	}
	return proteinSeq, codedBy, nil
}

func parseCodedBy(value string) (string, []segment, bool, error) {
	clean := strings.TrimSpace(value)
	accession := ""
	complement := false
	for strings.HasPrefix(clean, "complement(") && strings.HasSuffix(clean, ")") {
		complement = true
		clean = strings.TrimSuffix(strings.TrimPrefix(clean, "complement("), ")")
	}
	if strings.HasPrefix(clean, "join(") && strings.HasSuffix(clean, ")") {
		clean = strings.TrimSuffix(strings.TrimPrefix(clean, "join("), ")")
	}
	parts := strings.Split(clean, ",")
	var segments []segment
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		loc := part
		if idx := strings.Index(part, ":"); idx != -1 {
			if accession == "" {
				accession = strings.TrimSpace(part[:idx])
			}
			loc = part[idx+1:]
		}
		segParts, segComplement := parseLocation(loc)
		if segComplement {
			complement = true
		}
		segments = append(segments, segParts...)
	}
	if accession == "" {
		return "", nil, false, errors.New("coded_by missing accession")
	}
	if len(segments) == 0 {
		return "", nil, false, errors.New("coded_by has no segments")
	}
	return accession, segments, complement, nil
}

func parseLocation(loc string) ([]segment, bool) {
	clean := strings.TrimSpace(loc)
	complement := false
	if strings.HasPrefix(clean, "complement(") && strings.HasSuffix(clean, ")") {
		complement = true
		clean = strings.TrimPrefix(clean, "complement(")
		clean = strings.TrimSuffix(clean, ")")
	}
	if strings.HasPrefix(clean, "join(") && strings.HasSuffix(clean, ")") {
		clean = strings.TrimPrefix(clean, "join(")
		clean = strings.TrimSuffix(clean, ")")
	}
	parts := strings.Split(clean, ",")
	var segments []segment
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if strings.Contains(part, ":") {
			part = strings.SplitN(part, ":", 2)[1]
		}
		if strings.Contains(part, "..") {
			rangeParts := strings.SplitN(part, "..", 2)
			start := parseInt(strings.TrimLeft(rangeParts[0], "<>"))
			end := parseInt(strings.TrimLeft(rangeParts[1], "<>"))
			if start > 0 && end > 0 {
				segments = append(segments, segment{Start: start, End: end})
			}
		}
	}
	return segments, complement
}

func extractSequenceRegion(sequence string, segments []segment, complement bool) string {
	var builder strings.Builder
	for _, seg := range segments {
		start := seg.Start - 1
		end := seg.End
		if start < 0 || end > len(sequence) || start >= end {
			continue
		}
		builder.WriteString(sequence[start:end])
	}
	result := builder.String()
	if complement {
		result = reverseComplement(result)
	}
	return result
}

func applyResidueRange(cds, protein, rangeStr string) (string, string, error) {
	if protein == "" {
		protein = translate(cds)
	}
	start, end, err := parseResidueRange(rangeStr, len(protein))
	if err != nil {
		return "", "", err
	}
	dnaStart := (start - 1) * 3
	dnaEnd := end * 3
	if dnaStart < 0 || dnaEnd > len(cds) {
		return "", "", fmt.Errorf("residue range %s out of bounds for CDS length", rangeStr)
	}
	return cds[dnaStart:dnaEnd], protein[start-1 : end], nil
}

func parseResidueRange(rangeStr string, max int) (int, int, error) {
	parts := strings.Split(rangeStr, "-")
	if len(parts) != 2 {
		return 0, 0, fmt.Errorf("invalid residue range: %s", rangeStr)
	}
	startStr := strings.TrimSpace(parts[0])
	endStr := strings.TrimSpace(parts[1])
	start := 1
	end := max
	if startStr != "" {
		start = parseInt(startStr)
	}
	if endStr != "" {
		end = parseInt(endStr)
	}
	if start < 1 || end < 1 || start > end || end > max {
		return 0, 0, fmt.Errorf("invalid residue range: %s (valid 1-%d)", rangeStr, max)
	}
	return start, end, nil
}

func buildConstruct(vector Vector, insert seqInfo, method string) (Construct, ValidationResult, error) {
	if vector.InsertionSite <= 0 {
		return Construct{}, ValidationResult{}, errors.New("vector insertion_site is missing")
	}
	constructSeq, err := assembleConstruct(vector, insert.DNA, method)
	if err != nil {
		return Construct{}, ValidationResult{}, err
	}
	features := buildFeatures(vector, insert, len(insert.DNA))
	name := sanitizeName(fmt.Sprintf("%s_%s", vector.Name, insert.Name))
	desc := fmt.Sprintf("%s in %s vector", insert.Name, vector.Name)
	if insert.Range != "" {
		desc = fmt.Sprintf("%s(%s) in %s vector", insert.Name, insert.Range, vector.Name)
	}
	if vector.NTerminalTag != "" {
		desc = fmt.Sprintf("%s-%s", vector.NTerminalTag, desc)
	}
	construct := Construct{
		Name:            name,
		Description:     desc,
		Sequence:        constructSeq,
		Length:          len(constructSeq),
		Vector:          vector.Name,
		InsertName:      insert.Name,
		InsertSource:    insert.Source,
		InsertRange:     insert.Range,
		CloningMethod:   method,
		Features:        features,
		ExpectedProtein: "",
		InsertProtein:   insert.Protein,
		InsertDNA:       insert.DNA,
		CreatedDate:     time.Now().Format("02-Jan-2006"),
	}

	validation := validateConstruct(vector, construct, insert)
	construct.ExpectedProtein = validation.FusionProtein
	return construct, validation, nil
}

func assembleConstruct(vector Vector, insert string, method string) (string, error) {
	cutIndex := vector.InsertionSite - 1
	if cutIndex < 0 || cutIndex > len(vector.Sequence) {
		return "", fmt.Errorf("insertion_site %d outside vector length %d", vector.InsertionSite, len(vector.Sequence))
	}
	switch strings.ToLower(method) {
	case "lic", "gibson", "slic":
		return vector.Sequence[:cutIndex] + insert + vector.Sequence[cutIndex:], nil
	case "restriction":
		if len(vector.RestrictionSites) < 2 {
			return "", errors.New("restriction cloning requires two restriction sites in vector definition")
		}
		return assembleRestriction(vector, insert)
	default:
		return "", fmt.Errorf("unsupported cloning method: %s", method)
	}
}

func assembleRestriction(vector Vector, insert string) (string, error) {
	site5, ok := restrictionSites[vector.RestrictionSites[0]]
	if !ok {
		return "", fmt.Errorf("unknown restriction site: %s", vector.RestrictionSites[0])
	}
	site3, ok := restrictionSites[vector.RestrictionSites[1]]
	if !ok {
		return "", fmt.Errorf("unknown restriction site: %s", vector.RestrictionSites[1])
	}
	pos5 := strings.Index(vector.Sequence, site5.Sequence)
	pos3 := strings.Index(vector.Sequence, site3.Sequence)
	if pos5 == -1 || pos3 == -1 {
		return "", errors.New("restriction sites not found in vector sequence")
	}
	if pos5 >= pos3 {
		return "", errors.New("restriction site order is invalid")
	}
	vector5 := vector.Sequence[:pos5+site5.CutIndex]
	vector3 := vector.Sequence[pos3+site3.CutIndex:]
	return vector5 + insert + vector3, nil
}

func buildFeatures(vector Vector, insert seqInfo, insertLength int) []Feature {
	cutIndex := vector.InsertionSite - 1
	features := make([]Feature, 0, len(vector.Features)+3)
	for _, feat := range vector.Features {
		updated := feat
		if feat.Start > 0 && feat.End > 0 && feat.Start-1 >= cutIndex {
			updated.Start += insertLength
			updated.End += insertLength
		}
		if feat.Location != "" {
			updated.Location = feat.Location
		}
		features = append(features, updated)
	}

	insertStart := vector.InsertionSite
	insertEnd := vector.InsertionSite + insertLength - 1
	insertFeature := Feature{
		Name:   insert.Name,
		Type:   "CDS",
		Start:  insertStart,
		End:    insertEnd,
		Strand: "+",
		Qualifiers: map[string]string{
			"label": insert.Name,
		},
	}
	if insert.Source != "" {
		note := fmt.Sprintf("Insert: %s", insert.Source)
		if insert.Range != "" {
			note += fmt.Sprintf(", residues %s", insert.Range)
		}
		insertFeature.Qualifiers["note"] = note
	}
	if insert.Protein != "" {
		insertFeature.Qualifiers["translation"] = insert.Protein
	}
	features = append(features, insertFeature)

	tagFeature := findTagFeature(vector, cutIndex)
	if tagFeature != nil {
		location := fmt.Sprintf("join(%d..%d,%d..%d)", tagFeature.Start, tagFeature.End, insertStart, insertEnd)
		fusion := Feature{
			Name:     fmt.Sprintf("%s-%s", tagFeature.Name, insert.Name),
			Type:     "CDS",
			Strand:   "+",
			Location: location,
			Qualifiers: map[string]string{
				"label": fmt.Sprintf("%s-%s", tagFeature.Name, insert.Name),
			},
		}
		if insert.Protein != "" && vector.NTerminalTag != "" {
			fusion.Qualifiers["translation"] = vector.NTerminalTag + insert.Protein
		}
		features = append(features, fusion)
	}

	return features
}

func findTagFeature(vector Vector, cutIndex int) *Feature {
	for i := range vector.Features {
		feat := &vector.Features[i]
		if strings.ToLower(feat.Type) == "cds" && feat.End == cutIndex && feat.Strand != "-" {
			return feat
		}
	}
	return nil
}

func validateConstruct(vector Vector, construct Construct, insert seqInfo) ValidationResult {
	var warnings []string
	var errorsList []string

	if insert.DNA == "" {
		errorsList = append(errorsList, "insert sequence is empty")
	}
	if vector.ReadingFrame >= 0 {
		if (vector.InsertionSite-1)%3 != vector.ReadingFrame {
			warnings = append(warnings, fmt.Sprintf("insertion site frame mismatch (expected frame %d)", vector.ReadingFrame))
		}
		if len(insert.DNA)%3 != 0 {
			warnings = append(warnings, "insert length is not a multiple of 3")
		}
	}
	if vector.NTerminalTag == "" && !strings.HasPrefix(insert.DNA, "ATG") {
		warnings = append(warnings, "insert does not start with ATG and no N-terminal tag provided")
	}

	if hasInternalStop(insert.Protein) {
		warnings = append(warnings, "insert protein contains internal stop codon")
	}
	fusionProtein := insert.Protein
	if isAminoAcidSequence(vector.NTerminalTag) {
		fusionProtein = vector.NTerminalTag + insert.Protein
	}
	if hasInternalStop(fusionProtein) {
		warnings = append(warnings, "fusion protein contains internal stop codon")
	}

	return ValidationResult{
		Valid:             len(errorsList) == 0,
		Warnings:          warnings,
		Errors:            errorsList,
		FusionProtein:     fusionProtein,
		FusionLengthAA:    len(fusionProtein),
		ConstructLengthBP: len(construct.Sequence),
	}
}

func writeGenBank(construct Construct, filepath string) error {
	var buf bytes.Buffer
	date := time.Now().Format("02-Jan-2006")
	name := construct.Name
	if len(name) > 16 {
		name = name[:16]
	}
	fmt.Fprintf(&buf, "LOCUS       %-16s %7d bp    DNA     circular SYN %s\n", name, construct.Length, strings.ToUpper(date))
	fmt.Fprintf(&buf, "DEFINITION  %s\n", construct.Description)
	fmt.Fprintf(&buf, "ACCESSION   .\n")
	fmt.Fprintf(&buf, "VERSION     .\n")
	fmt.Fprintf(&buf, "KEYWORDS    .\n")
	fmt.Fprintf(&buf, "SOURCE      synthetic construct\n")
	fmt.Fprintf(&buf, "  ORGANISM  synthetic construct\n")
	fmt.Fprintf(&buf, "            other sequences; artificial sequences.\n")
	fmt.Fprintf(&buf, "FEATURES             Location/Qualifiers\n")
	fmt.Fprintf(&buf, "     source          1..%d\n", construct.Length)
	fmt.Fprintf(&buf, "                     /organism=\"synthetic construct\"\n")
	fmt.Fprintf(&buf, "                     /mol_type=\"other DNA\"\n")

	for _, feature := range construct.Features {
		location := feature.Location
		if location == "" {
			location = formatLocation(feature)
		}
		fmt.Fprintf(&buf, "     %-15s %s\n", feature.Type, location)
		label := feature.Name
		if feature.Qualifiers != nil {
			if lbl, ok := feature.Qualifiers["label"]; ok {
				label = lbl
			}
		}
		if label != "" {
			fmt.Fprintf(&buf, "                     /label=\"%s\"\n", escapeGenBank(label))
		}
		keys := make([]string, 0, len(feature.Qualifiers))
		for key := range feature.Qualifiers {
			if key == "label" {
				continue
			}
			keys = append(keys, key)
		}
		sort.Strings(keys)
		for _, key := range keys {
			fmt.Fprintf(&buf, "                     /%s=\"%s\"\n", key, escapeGenBank(feature.Qualifiers[key]))
		}
	}

	fmt.Fprintf(&buf, "ORIGIN\n")
	writeOrigin(&buf, construct.Sequence)
	fmt.Fprintf(&buf, "//\n")

	return os.WriteFile(filepath, buf.Bytes(), 0644)
}

func writeOrigin(buf *bytes.Buffer, sequence string) {
	seq := strings.ToLower(sequence)
	for i := 0; i < len(seq); i += 60 {
		chunkEnd := i + 60
		if chunkEnd > len(seq) {
			chunkEnd = len(seq)
		}
		lineSeq := seq[i:chunkEnd]
		fmt.Fprintf(buf, "%9d ", i+1)
		for j := 0; j < len(lineSeq); j += 10 {
			end := j + 10
			if end > len(lineSeq) {
				end = len(lineSeq)
			}
			fmt.Fprintf(buf, "%s ", lineSeq[j:end])
		}
		fmt.Fprintln(buf)
	}
}

func formatLocation(feature Feature) string {
	start := feature.Start
	end := feature.End
	if start <= 0 || end <= 0 {
		return "1..1"
	}
	location := fmt.Sprintf("%d..%d", start, end)
	if feature.Strand == "-" {
		location = fmt.Sprintf("complement(%s)", location)
	}
	return location
}

func escapeGenBank(value string) string {
	return strings.ReplaceAll(value, "\"", "'")
}

func writeJSON(construct Construct, path string) error {
	data, err := json.MarshalIndent(construct, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0644)
}

func readSequenceFile(path string) (string, string, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return "", "", err
	}
	text := strings.TrimSpace(string(content))
	if strings.HasPrefix(text, ">") {
		return parseFasta(text)
	}
	if strings.Contains(text, "LOCUS") && strings.Contains(text, "ORIGIN") {
		name, seq := parseGenBankSequence(text)
		return name, seq, nil
	}
	return "", normalizeDNA(text), nil
}

func parseFasta(content string) (string, string, error) {
	lines := strings.Split(content, "\n")
	if len(lines) == 0 {
		return "", "", errors.New("empty FASTA")
	}
	name := strings.TrimSpace(strings.TrimPrefix(lines[0], ">"))
	var builder strings.Builder
	for _, line := range lines[1:] {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		builder.WriteString(line)
	}
	return name, normalizeDNA(builder.String()), nil
}

func normalizeDNA(seq string) string {
	var builder strings.Builder
	for _, ch := range seq {
		switch ch {
		case 'A', 'C', 'G', 'T', 'N':
			builder.WriteRune(ch)
		case 'a', 'c', 'g', 't', 'n':
			builder.WriteRune(ch - 'a' + 'A')
		}
	}
	return builder.String()
}

func reverseComplement(seq string) string {
	var builder strings.Builder
	for i := len(seq) - 1; i >= 0; i-- {
		switch seq[i] {
		case 'A':
			builder.WriteByte('T')
		case 'T':
			builder.WriteByte('A')
		case 'C':
			builder.WriteByte('G')
		case 'G':
			builder.WriteByte('C')
		default:
			builder.WriteByte('N')
		}
	}
	return builder.String()
}

func translate(dna string) string {
	dna = normalizeDNA(dna)
	var builder strings.Builder
	for i := 0; i+2 < len(dna); i += 3 {
		codon := dna[i : i+3]
		aa, ok := codonTable[codon]
		if !ok {
			aa = "X"
		}
		builder.WriteString(aa)
	}
	return builder.String()
}

func sanitizeName(name string) string {
	name = strings.TrimSpace(name)
	name = strings.ReplaceAll(name, " ", "_")
	name = strings.ReplaceAll(name, "/", "_")
	name = strings.ReplaceAll(name, "(", "")
	name = strings.ReplaceAll(name, ")", "")
	return name
}

func hasInternalStop(protein string) bool {
	if len(protein) <= 1 {
		return false
	}
	return strings.Contains(protein[:len(protein)-1], "*")
}

func isAminoAcidSequence(seq string) bool {
	if seq == "" {
		return false
	}
	for _, ch := range seq {
		if ch == '-' || ch == ' ' {
			return false
		}
		if ch < 'A' || ch > 'Z' {
			return false
		}
	}
	return true
}

var codonTable = map[string]string{
	"TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
	"TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
	"TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
	"TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
	"CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
	"CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
	"CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
	"CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
	"ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
	"ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
	"AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
	"AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
	"GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
	"GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
	"GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
	"GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}
