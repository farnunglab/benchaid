package main

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	defaultBaseURL = "https://twist-api.twistdna.com"
)

type client struct {
	baseURL string
	email   string
	token   string
	http    *http.Client
}

func main() {
	loadEnvFromFile(".env")

	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}

	cmd := os.Args[1]
	switch cmd {
	case "gene":
		runGene(os.Args[2:])
	case "gene-block", "gene-blocks", "geneBlock":
		runFragment(os.Args[2:])
	case "fragment":
		runFragment(os.Args[2:])
	case "vectors":
		runVectors(os.Args[2:])
	default:
		usage()
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintf(os.Stderr, "Twist DNA ordering CLI\n\n")
	fmt.Fprintf(os.Stderr, "Usage:\n")
	fmt.Fprintf(os.Stderr, "  twist_order gene --sequence <DNA> --name <NAME> --vector-id <ID> --insertion-point-id <ID> --recipient-address-id <ID> --first-name <FN> --last-name <LN> --phone <PHONE> [--payment-method-id <ID> | --no-po]\n")
	fmt.Fprintf(os.Stderr, "  twist_order fragment --sequence <DNA> --name <NAME> --recipient-address-id <ID> --first-name <FN> --last-name <LN> --phone <PHONE> [--payment-method-id <ID> | --no-po]\n")
	fmt.Fprintf(os.Stderr, "  twist_order gene-block --sequence <DNA> --name <NAME> --recipient-address-id <ID> --first-name <FN> --last-name <LN> --phone <PHONE> [--payment-method-id <ID> | --no-po]\n")
	fmt.Fprintf(os.Stderr, "  twist_order vectors list\n\n")
	fmt.Fprintf(os.Stderr, "Env (from .env): TWIST_API_TOKEN, TWIST_USER_EMAIL, TWIST_API_BASE_URL\n")
}

func runGene(args []string) {
	cfg := newOrderFlags("gene")
	cfg.fs.Parse(args)

	if cfg.sequence == "" && cfg.sequenceFile == "" {
		fatalf("provide --sequence or --sequence-file")
	}
	if cfg.vectorID == "" || cfg.insertionPointID == "" {
		fatalf("gene orders require --vector-id and --insertion-point-id")
	}
	if err := cfg.validateShipment(); err != nil {
		fatalf("%v", err)
	}

	seq, err := readSequence(cfg.sequence, cfg.sequenceFile)
	if err != nil {
		fatalf("failed to read sequence: %v", err)
	}

	c := cfg.client()
	constructID, err := c.createConstruct(constructRequest{
		Sequences:         []string{seq},
		Name:              cfg.name,
		Type:              "CLONED_GENE",
		VectorMESUID:      cfg.vectorID,
		InsertionPointMES: cfg.insertionPointID,
		AdaptersOn:        nil,
	})
	if err != nil {
		fatalf("construct creation failed: %v", err)
	}
	fmt.Fprintf(os.Stderr, "Construct created: %s\n", constructID)

	if err := c.waitForScoring(constructID, cfg.scoringWait, cfg.scoringInterval); err != nil {
		fatalf("scoring failed: %v", err)
	}

	orderSubProduct := "CLONAL_GENES_SHORT"
	orderSettings := []map[string]interface{}{
		{
			"name":         "DNA Scale",
			"product_code": cfg.dnaScale,
		},
		{
			"name":         "Delivery Format",
			"product_code": cfg.deliveryFormat,
			"configuration": map[string]string{
				"fill_method": "Vertical",
			},
		},
	}
	if cfg.glycerolStock {
		orderSettings = append(orderSettings, map[string]interface{}{
			"name":         "Glycerol Stock",
			"product_code": "SER_PKG_GLYC",
		})
	}
	if cfg.bufferCode != "" {
		orderSettings = append(orderSettings, map[string]interface{}{
			"name":         "Buffer",
			"product_code": cfg.bufferCode,
		})
	}
	if cfg.normalization > 0 {
		orderSettings = append(orderSettings, map[string]interface{}{
			"name":         "Normalization",
			"product_code": "GENE_PREP_NORM",
			"value":        cfg.normalization,
		})
	}

	quoteID, err := c.createQuote(quoteRequest{
		ExternalID: cfg.externalID,
		Project:    cfg.projectName,
		Shipment: shipment{
			FirstName:          cfg.firstName,
			LastName:           cfg.lastName,
			Phone:              cfg.phone,
			RecipientAddressID: cfg.recipientAddressID,
		},
		ConstructID:     constructID,
		OrderSubProduct: orderSubProduct,
		OrderSettings:   orderSettings,
	})
	if err != nil {
		fatalf("quote creation failed: %v", err)
	}
	fmt.Fprintf(os.Stderr, "Quote created: %s\n", quoteID)

	if err := c.waitForQuote(quoteID, cfg.quoteWait, cfg.quoteInterval); err != nil {
		fatalf("quote failed: %v", err)
	}

	if cfg.quoteOnly {
		fmt.Fprintf(os.Stderr, "Quote ready. Skipping order creation (--quote-only).\n")
		return
	}

	orderID, err := c.createOrder(quoteID, cfg.paymentMethodID, cfg.poReference, cfg.noPO)
	if err != nil {
		fatalf("order creation failed: %v", err)
	}
	fmt.Printf("Order created: %s\n", orderID)
}

func runFragment(args []string) {
	cfg := newOrderFlags("fragment")
	cfg.fs.Parse(args)

	if cfg.sequence == "" && cfg.sequenceFile == "" {
		fatalf("provide --sequence or --sequence-file")
	}
	if err := cfg.validateShipment(); err != nil {
		fatalf("%v", err)
	}

	seq, err := readSequence(cfg.sequence, cfg.sequenceFile)
	if err != nil {
		fatalf("failed to read sequence: %v", err)
	}

	adaptersOn := cfg.adaptersOn
	c := cfg.client()
	constructID, err := c.createConstruct(constructRequest{
		Sequences:  []string{seq},
		Name:       cfg.name,
		Type:       "NON_CLONED_GENE",
		AdaptersOn: &adaptersOn,
	})
	if err != nil {
		fatalf("construct creation failed: %v", err)
	}
	fmt.Fprintf(os.Stderr, "Construct created: %s\n", constructID)

	if err := c.waitForScoring(constructID, cfg.scoringWait, cfg.scoringInterval); err != nil {
		fatalf("scoring failed: %v", err)
	}

	orderSubProduct := "NON_CLONAL_ADAPTERS_OFF"
	if adaptersOn {
		orderSubProduct = "NON_CLONAL_ADAPTERS_ON"
	}

	orderSettings := []map[string]interface{}{
		{
			"name":         "Delivery Format",
			"product_code": cfg.deliveryFormat,
			"configuration": map[string]string{
				"fill_method": "Vertical",
			},
		},
	}
	if cfg.bufferCode != "" {
		orderSettings = append(orderSettings, map[string]interface{}{
			"name":         "Buffer",
			"product_code": cfg.bufferCode,
		})
	}
	if cfg.normalization > 0 {
		code := "ADO_NORM"
		if adaptersOn {
			code = "AD_NORM"
		}
		orderSettings = append(orderSettings, map[string]interface{}{
			"name":         "Normalization",
			"product_code": code,
			"value":        cfg.normalization,
		})
	}

	quoteID, err := c.createQuote(quoteRequest{
		ExternalID: cfg.externalID,
		Project:    cfg.projectName,
		Shipment: shipment{
			FirstName:          cfg.firstName,
			LastName:           cfg.lastName,
			Phone:              cfg.phone,
			RecipientAddressID: cfg.recipientAddressID,
		},
		ConstructID:     constructID,
		OrderSubProduct: orderSubProduct,
		OrderSettings:   orderSettings,
	})
	if err != nil {
		fatalf("quote creation failed: %v", err)
	}
	fmt.Fprintf(os.Stderr, "Quote created: %s\n", quoteID)

	if err := c.waitForQuote(quoteID, cfg.quoteWait, cfg.quoteInterval); err != nil {
		fatalf("quote failed: %v", err)
	}

	if cfg.quoteOnly {
		fmt.Fprintf(os.Stderr, "Quote ready. Skipping order creation (--quote-only).\n")
		return
	}

	orderID, err := c.createOrder(quoteID, cfg.paymentMethodID, cfg.poReference, cfg.noPO)
	if err != nil {
		fatalf("order creation failed: %v", err)
	}
	fmt.Printf("Order created: %s\n", orderID)
}

func runVectors(args []string) {
	if len(args) < 1 {
		fmt.Fprintf(os.Stderr, "Usage: twist_order vectors list\n")
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		cfg := newOrderFlags("vectors")
		cfg.fs.Parse(args[1:])
		c := cfg.client()
		data, err := c.getJSON(fmt.Sprintf("/v1/users/%s/vectors/", pathEscape(cfg.email)))
		if err != nil {
			fatalf("vector list failed: %v", err)
		}
		fmt.Println(string(data))
	default:
		fmt.Fprintf(os.Stderr, "Usage: twist_order vectors list\n")
		os.Exit(1)
	}
}

type orderFlags struct {
	fs *flag.FlagSet

	sequence         string
	sequenceFile     string
	name             string
	projectName      string
	externalID       string
	vectorID         string
	insertionPointID string
	adaptersOn       bool
	dnaScale         string
	deliveryFormat   string
	bufferCode       string
	normalization    float64
	glycerolStock    bool

	email              string
	token              string
	baseURL            string
	firstName          string
	lastName           string
	phone              string
	recipientAddressID string

	paymentMethodID string
	poReference     string
	noPO            bool
	quoteOnly       bool

	scoringWait     time.Duration
	scoringInterval time.Duration
	quoteWait       time.Duration
	quoteInterval   time.Duration
}

func newOrderFlags(name string) *orderFlags {
	fs := flag.NewFlagSet(name, flag.ExitOnError)
	cfg := &orderFlags{fs: fs}

	fs.StringVar(&cfg.sequence, "sequence", "", "DNA sequence (A/C/T/G)")
	fs.StringVar(&cfg.sequenceFile, "sequence-file", "", "Path to file containing DNA sequence")
	fs.StringVar(&cfg.name, "name", "Twist_Construct", "Construct name")
	fs.StringVar(&cfg.projectName, "project-name", "", "Optional project name for quote PDF")
	fs.StringVar(&cfg.externalID, "external-id", "", "Optional external ID for quote")
	fs.StringVar(&cfg.vectorID, "vector-id", "", "Vector MES UID (required for clonal genes)")
	fs.StringVar(&cfg.insertionPointID, "insertion-point-id", "", "Insertion point MES UID (required for clonal genes)")
	fs.BoolVar(&cfg.adaptersOn, "adapters-on", false, "Enable adapters for gene fragments")
	fs.StringVar(&cfg.dnaScale, "dna-scale", "GENE_PREP_MICRO", "Clonal gene DNA scale product code")
	fs.StringVar(&cfg.deliveryFormat, "delivery-format", "SER_PKG_TUBE", "Delivery format product code")
	fs.StringVar(&cfg.bufferCode, "buffer-code", "", "Optional buffer product code")
	fs.Float64Var(&cfg.normalization, "normalization", 0, "Normalization value (0.5-2.0 for clonal genes)")
	fs.BoolVar(&cfg.glycerolStock, "glycerol-stock", false, "Add glycerol stock for clonal genes")

	fs.StringVar(&cfg.email, "email", os.Getenv("TWIST_USER_EMAIL"), "Twist user email (path param)")
	fs.StringVar(&cfg.token, "token", os.Getenv("TWIST_API_TOKEN"), "Twist API token (X-End-User-Token)")
	fs.StringVar(&cfg.baseURL, "base-url", envOrDefault("TWIST_API_BASE_URL", defaultBaseURL), "Twist API base URL")

	fs.StringVar(&cfg.firstName, "first-name", "", "Shipment first name")
	fs.StringVar(&cfg.lastName, "last-name", "", "Shipment last name")
	fs.StringVar(&cfg.phone, "phone", "", "Shipment phone")
	fs.StringVar(&cfg.recipientAddressID, "recipient-address-id", "", "Shipment recipient address ID")

	fs.StringVar(&cfg.paymentMethodID, "payment-method-id", "", "Payment method ID")
	fs.StringVar(&cfg.poReference, "po-reference", "", "PO reference (optional)")
	fs.BoolVar(&cfg.noPO, "no-po", false, "Create order without PO")
	fs.BoolVar(&cfg.quoteOnly, "quote-only", false, "Only create quote, skip order")

	fs.DurationVar(&cfg.scoringWait, "scoring-timeout", 10*time.Minute, "Max time to wait for construct scoring")
	fs.DurationVar(&cfg.scoringInterval, "scoring-interval", 15*time.Second, "Polling interval for construct scoring")
	fs.DurationVar(&cfg.quoteWait, "quote-timeout", 10*time.Minute, "Max time to wait for quote status")
	fs.DurationVar(&cfg.quoteInterval, "quote-interval", 15*time.Second, "Polling interval for quote status")

	return cfg
}

func (c *orderFlags) validateShipment() error {
	if c.email == "" || c.token == "" {
		return errors.New("TWIST_USER_EMAIL and TWIST_API_TOKEN must be set (or pass --email/--token)")
	}
	if c.firstName == "" || c.lastName == "" || c.phone == "" || c.recipientAddressID == "" {
		return errors.New("shipment fields required: --first-name, --last-name, --phone, --recipient-address-id")
	}
	if !c.noPO && !c.quoteOnly && c.paymentMethodID == "" {
		return errors.New("provide --payment-method-id or use --no-po")
	}
	return nil
}

func (c *orderFlags) client() *client {
	return &client{
		baseURL: strings.TrimRight(c.baseURL, "/"),
		email:   c.email,
		token:   c.token,
		http:    &http.Client{Timeout: 60 * time.Second},
	}
}

type constructRequest struct {
	Sequences         []string `json:"sequences"`
	Name              string   `json:"name"`
	Type              string   `json:"type"`
	VectorMESUID      string   `json:"vector_mes_uid,omitempty"`
	InsertionPointMES string   `json:"insertion_point_mes_uid,omitempty"`
	AdaptersOn        *bool    `json:"adapters_on,omitempty"`
}

type constructResponse struct {
	ID string `json:"id"`
}

func (c *client) createConstruct(req constructRequest) (string, error) {
	payload, err := json.Marshal(req)
	if err != nil {
		return "", err
	}
	path := fmt.Sprintf("/v1/users/%s/constructs/", pathEscape(c.email))
	resp, err := c.request(http.MethodPost, path, payload)
	if err != nil {
		return "", err
	}
	var out constructResponse
	if err := json.Unmarshal(resp, &out); err != nil {
		return "", err
	}
	if out.ID == "" {
		return "", errors.New("missing construct id in response")
	}
	return out.ID, nil
}

type constructStatus struct {
	ID        string `json:"id"`
	Scored    bool   `json:"scored"`
	ScoreData struct {
		Issues []map[string]interface{} `json:"issues"`
	} `json:"score_data"`
}

func (c *client) waitForScoring(id string, timeout, interval time.Duration) error {
	deadline := time.Now().Add(timeout)
	for {
		status, err := c.fetchConstructStatus(id)
		if err != nil {
			return err
		}
		if status.Scored {
			if len(status.ScoreData.Issues) > 0 {
				return fmt.Errorf("scoring issues returned: %v", status.ScoreData.Issues)
			}
			fmt.Fprintf(os.Stderr, "Scoring complete: %s\n", id)
			return nil
		}
		if time.Now().After(deadline) {
			return errors.New("scoring timeout exceeded")
		}
		time.Sleep(interval)
	}
}

func (c *client) fetchConstructStatus(id string) (constructStatus, error) {
	path := fmt.Sprintf("/v1/users/%s/constructs/describe/?id__in=%s&scored=true", pathEscape(c.email), queryEscape(id))
	raw, err := c.getJSON(path)
	if err != nil {
		return constructStatus{}, err
	}
	var items []constructStatus
	if err := json.Unmarshal(raw, &items); err != nil {
		return constructStatus{}, err
	}
	if len(items) == 0 {
		return constructStatus{}, errors.New("no construct status returned")
	}
	return items[0], nil
}

type shipment struct {
	FirstName          string `json:"first_name"`
	LastName           string `json:"last_name"`
	Phone              string `json:"phone"`
	RecipientAddressID string `json:"recipient_address_id"`
}

type quoteRequest struct {
	ExternalID      string                   `json:"external_id"`
	Project         string                   `json:"ecommerce_project_name,omitempty"`
	Shipment        shipment                 `json:"shipment"`
	ConstructID     string                   `json:"-"`
	OrderSubProduct string                   `json:"order_sub_product_type"`
	OrderSettings   []map[string]interface{} `json:"order_settings,omitempty"`
}

func (c *client) createQuote(req quoteRequest) (string, error) {
	if req.ExternalID == "" {
		req.ExternalID = "twist-" + randomID(6)
	}
	payload := map[string]interface{}{
		"external_id": req.ExternalID,
		"shipment": map[string]string{
			"first_name":           req.Shipment.FirstName,
			"last_name":            req.Shipment.LastName,
			"phone":                req.Shipment.Phone,
			"recipient_address_id": req.Shipment.RecipientAddressID,
		},
		"containers": []map[string]interface{}{
			{
				"constructs": []map[string]interface{}{
					{
						"id":    req.ConstructID,
						"index": 1,
					},
				},
			},
		},
		"order_sub_product_type": req.OrderSubProduct,
	}
	if req.Project != "" {
		payload["ecommerce_project_name"] = req.Project
	}
	if len(req.OrderSettings) > 0 {
		payload["order_settings"] = req.OrderSettings
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	path := fmt.Sprintf("/v1/users/%s/quotes/", pathEscape(c.email))
	resp, err := c.request(http.MethodPost, path, body)
	if err != nil {
		return "", err
	}
	var out map[string]interface{}
	if err := json.Unmarshal(resp, &out); err != nil {
		return "", err
	}
	id, _ := out["id"].(string)
	if id == "" {
		return "", errors.New("missing quote id in response")
	}
	return id, nil
}

func (c *client) waitForQuote(id string, timeout, interval time.Duration) error {
	deadline := time.Now().Add(timeout)
	for {
		status, err := c.fetchQuoteStatus(id)
		if err != nil {
			return err
		}
		if status == "SUCCESS" {
			fmt.Fprintf(os.Stderr, "Quote status: %s\n", status)
			return nil
		}
		if status == "FAILED" {
			return errors.New("quote failed")
		}
		if time.Now().After(deadline) {
			return errors.New("quote timeout exceeded")
		}
		time.Sleep(interval)
	}
}

func (c *client) fetchQuoteStatus(id string) (string, error) {
	path := fmt.Sprintf("/v1/users/%s/quotes/%s/", pathEscape(c.email), pathEscape(id))
	raw, err := c.getJSON(path)
	if err != nil {
		return "", err
	}
	var out struct {
		StatusInfo struct {
			Status string `json:"status"`
		} `json:"status_info"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return "", err
	}
	if out.StatusInfo.Status == "" {
		return "", errors.New("missing quote status")
	}
	return out.StatusInfo.Status, nil
}

func (c *client) createOrder(quoteID, paymentMethodID, poReference string, noPO bool) (string, error) {
	payload := map[string]interface{}{
		"quote_id": quoteID,
	}
	if noPO {
		payload["payment_flow"] = "NO_PO"
		payload["payment_method_id"] = nil
	} else {
		payload["payment_method_id"] = paymentMethodID
		if poReference != "" {
			payload["po_reference"] = poReference
		}
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	path := fmt.Sprintf("/v1/users/%s/orders/", pathEscape(c.email))
	resp, err := c.request(http.MethodPost, path, body)
	if err != nil {
		return "", err
	}
	var out map[string]interface{}
	if err := json.Unmarshal(resp, &out); err != nil {
		return "", err
	}
	id, _ := out["id"].(string)
	if id == "" {
		return "", errors.New("missing order id in response")
	}
	return id, nil
}

func (c *client) getJSON(path string) ([]byte, error) {
	return c.request(http.MethodGet, path, nil)
}

func (c *client) request(method, path string, body []byte) ([]byte, error) {
	url := c.baseURL + path
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	req, err := http.NewRequest(method, url, reader)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-End-User-Token", c.token)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("twist api error (%d): %s", resp.StatusCode, strings.TrimSpace(string(respBody)))
	}
	return respBody, nil
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

func readSequence(seq, filePath string) (string, error) {
	if filePath == "" {
		clean := normalizeSequence(seq)
		if err := validateSequence(clean); err != nil {
			return "", err
		}
		return clean, nil
	}
	data, err := os.ReadFile(filepath.Clean(filePath))
	if err != nil {
		return "", err
	}
	clean := normalizeSequence(string(data))
	if err := validateSequence(clean); err != nil {
		return "", err
	}
	return clean, nil
}

func normalizeSequence(seq string) string {
	lines := strings.Split(seq, "\n")
	var b strings.Builder
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, ">") || strings.HasPrefix(line, ";") {
			continue
		}
		b.WriteString(line)
	}
	replacer := strings.NewReplacer(" ", "", "\r", "", "\t", "")
	return strings.ToUpper(replacer.Replace(b.String()))
}

func validateSequence(seq string) error {
	if seq == "" {
		return errors.New("sequence is empty after normalization")
	}
	for i := 0; i < len(seq); i++ {
		switch seq[i] {
		case 'A', 'C', 'G', 'T', 'N':
			continue
		default:
			return fmt.Errorf("invalid base %q at position %d", seq[i], i+1)
		}
	}
	return nil
}

func envOrDefault(key, def string) string {
	val := os.Getenv(key)
	if val == "" {
		return def
	}
	return val
}

func randomID(bytesLen int) string {
	buf := make([]byte, bytesLen)
	_, _ = rand.Read(buf)
	return hex.EncodeToString(buf)
}

func pathEscape(val string) string {
	return url.PathEscape(val)
}

func queryEscape(val string) string {
	return url.QueryEscape(val)
}

func fatalf(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}
