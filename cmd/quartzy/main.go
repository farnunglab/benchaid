package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

const defaultBaseURL = "https://api.quartzy.com"

type client struct {
	baseURL string
	token   string
	http    *http.Client
}

func main() {
	loadEnvFromFile(".env")

	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}

	switch os.Args[1] {
	case "health":
		runHealth(os.Args[2:])
	case "user":
		runUser(os.Args[2:])
	case "labs":
		runLabs(os.Args[2:])
	case "inventory":
		runInventory(os.Args[2:])
	case "order-requests":
		runOrderRequests(os.Args[2:])
	case "types":
		runTypes(os.Args[2:])
	case "webhooks":
		runWebhooks(os.Args[2:])
	default:
		usage()
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintf(os.Stderr, "Quartzy CLI\n\n")
	fmt.Fprintf(os.Stderr, "Usage:\n")
	fmt.Fprintf(os.Stderr, "  quartzy health\n")
	fmt.Fprintf(os.Stderr, "  quartzy user\n")
	fmt.Fprintf(os.Stderr, "  quartzy labs list [--organization-id <UUID>] [--page <N>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy labs get --id <UUID>\n")
	fmt.Fprintf(os.Stderr, "  quartzy inventory list [--lab-id <UUID>] [--page <N>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy inventory get --id <UUID>\n")
	fmt.Fprintf(os.Stderr, "  quartzy inventory update --id <UUID> --quantity <VALUE>\n")
	fmt.Fprintf(os.Stderr, "  quartzy order-requests list [--lab-id <UUID>] [--page <N>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy order-requests list --created [--lab-id <UUID>] [--page <N>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy order-requests list --status <PENDING|CREATED|CANCELLED|APPROVED|ORDERED|BACKORDERED|RECEIVED>[,<STATUS>...] [--lab-id <UUID>] [--page <N>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy order-requests get --id <UUID>\n")
	fmt.Fprintf(os.Stderr, "  quartzy order-requests create --lab-id <UUID> --type-id <UUID> --name <NAME> --vendor-name <NAME> --catalog-number <NUM> --price-amount <INT> --price-currency <CODE> --quantity <INT> [--vendor-product-id <UUID>] [--required-before <YYYY-MM-DD>] [--notes <TEXT>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy order-requests update --id <UUID> --status <CREATED|CANCELLED|APPROVED|ORDERED|BACKORDERED|RECEIVED>\n")
	fmt.Fprintf(os.Stderr, "  quartzy types list [--lab-id <UUID>] [--name <NAME>] [--page <N>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy webhooks list [--organization-id <UUID>] [--page <N>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy webhooks get --id <UUID>\n")
	fmt.Fprintf(os.Stderr, "  quartzy webhooks create --url <URL> (--lab-id <UUID> | --organization-id <UUID>) [--name <NAME>] [--event-types <CSV>] [--is-enabled <true|false>] [--is-verified <true|false>] [--is-signed <true|false>]\n")
	fmt.Fprintf(os.Stderr, "  quartzy webhooks update --id <UUID> --is-enabled <true|false>\n\n")
	fmt.Fprintf(os.Stderr, "Env (from .env): QUARTZY_KEY, QUARTZY_BASE_URL, QUARTZY_LAB_ID, QUARTZY_ORGANIZATION_ID\n")
}

func runHealth(args []string) {
	if len(args) != 0 {
		usage()
		os.Exit(1)
	}
	c := newClient("", false)
	resp, err := c.doRequest("GET", "/healthz", nil, nil)
	if err != nil {
		fatalf("health failed: %v", err)
	}
	printJSON(resp)
}

func runUser(args []string) {
	fs := flag.NewFlagSet("user", flag.ExitOnError)
	token := baseFlags(fs)
	fs.Parse(args)

	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/user", nil, nil)
	if err != nil {
		fatalf("user request failed: %v", err)
	}
	printJSON(resp)
}

func runLabs(args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		runLabsList(args[1:])
	case "get":
		runLabsGet(args[1:])
	default:
		usage()
		os.Exit(1)
	}
}

func runLabsList(args []string) {
	fs := flag.NewFlagSet("labs list", flag.ExitOnError)
	orgID := fs.String("organization-id", "", "Organization ID")
	page := fs.Int("page", 0, "Page number")
	token := baseFlags(fs)
	fs.Parse(args)

	query := url.Values{}
	orgValue := envOrFlag(*orgID, "QUARTZY_ORGANIZATION_ID")
	if orgValue != "" {
		query.Set("organization_id", orgValue)
	}
	if *page > 0 {
		query.Set("page", fmt.Sprintf("%d", *page))
	}

	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/labs", query, nil)
	if err != nil {
		fatalf("labs list failed: %v", err)
	}
	printJSON(resp)
}

func runLabsGet(args []string) {
	fs := flag.NewFlagSet("labs get", flag.ExitOnError)
	id := fs.String("id", "", "Lab ID")
	token := baseFlags(fs)
	fs.Parse(args)

	if *id == "" {
		fatalf("provide --id")
	}
	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/labs/"+url.PathEscape(*id), nil, nil)
	if err != nil {
		fatalf("labs get failed: %v", err)
	}
	printJSON(resp)
}

func runInventory(args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		runInventoryList(args[1:])
	case "get":
		runInventoryGet(args[1:])
	case "update":
		runInventoryUpdate(args[1:])
	default:
		usage()
		os.Exit(1)
	}
}

func runInventoryList(args []string) {
	fs := flag.NewFlagSet("inventory list", flag.ExitOnError)
	labID := fs.String("lab-id", "", "Lab ID")
	page := fs.Int("page", 0, "Page number")
	token := baseFlags(fs)
	fs.Parse(args)

	query := url.Values{}
	labValue := envOrFlag(*labID, "QUARTZY_LAB_ID")
	if labValue != "" {
		query.Set("lab_id", labValue)
	}
	if *page > 0 {
		query.Set("page", fmt.Sprintf("%d", *page))
	}

	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/inventory-items", query, nil)
	if err != nil {
		fatalf("inventory list failed: %v", err)
	}
	printJSON(resp)
}

func runInventoryGet(args []string) {
	fs := flag.NewFlagSet("inventory get", flag.ExitOnError)
	id := fs.String("id", "", "Inventory item ID")
	token := baseFlags(fs)
	fs.Parse(args)

	if *id == "" {
		fatalf("provide --id")
	}
	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/inventory-items/"+url.PathEscape(*id), nil, nil)
	if err != nil {
		fatalf("inventory get failed: %v", err)
	}
	printJSON(resp)
}

func runInventoryUpdate(args []string) {
	fs := flag.NewFlagSet("inventory update", flag.ExitOnError)
	id := fs.String("id", "", "Inventory item ID")
	quantity := fs.String("quantity", "", "Quantity")
	token := baseFlags(fs)
	fs.Parse(args)

	if *id == "" || *quantity == "" {
		fatalf("provide --id and --quantity")
	}

	body := map[string]string{
		"quantity": *quantity,
	}
	c := newClient(*token, true)
	resp, err := c.doRequest("PUT", "/inventory-items/"+url.PathEscape(*id), nil, body)
	if err != nil {
		fatalf("inventory update failed: %v", err)
	}
	printJSON(resp)
}

func runOrderRequests(args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		runOrderRequestsList(args[1:])
	case "get":
		runOrderRequestsGet(args[1:])
	case "create":
		runOrderRequestsCreate(args[1:])
	case "update":
		runOrderRequestsUpdate(args[1:])
	default:
		usage()
		os.Exit(1)
	}
}

func runOrderRequestsList(args []string) {
	fs := flag.NewFlagSet("order-requests list", flag.ExitOnError)
	labID := fs.String("lab-id", "", "Lab ID")
	page := fs.Int("page", 0, "Page number")
	status := fs.String("status", "", "Filter by status (comma-separated)")
	createdOnly := fs.Bool("created", false, "Only include pending status")
	token := baseFlags(fs)
	fs.Parse(args)

	query := url.Values{}
	labValue := envOrFlag(*labID, "QUARTZY_LAB_ID")
	if labValue != "" {
		query.Set("lab_id", labValue)
	}
	if *page > 0 {
		query.Set("page", fmt.Sprintf("%d", *page))
	}
	if *createdOnly && *status != "" {
		fatalf("use --created or --status, not both")
	}
	var statusFilters []string
	if *createdOnly {
		statusFilters = []string{"PENDING"}
	} else if *status != "" {
		statusFilters = splitCSV(*status)
		for _, entry := range statusFilters {
			if !isValidOrderStatus(entry) {
				fatalf("invalid --status: %s", entry)
			}
		}
	}
	for _, entry := range statusFilters {
		query.Add("status[]", entry)
	}

	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/order-requests", query, nil)
	if err != nil {
		fatalf("order-requests list failed: %v", err)
	}
	if len(statusFilters) > 0 {
		filtered, err := filterOrderRequests(resp, statusFilters)
		if err != nil {
			fatalf("filter order-requests failed: %v", err)
		}
		printJSON(filtered)
		return
	}
	printJSON(resp)
}

func runOrderRequestsGet(args []string) {
	fs := flag.NewFlagSet("order-requests get", flag.ExitOnError)
	id := fs.String("id", "", "Order request ID")
	token := baseFlags(fs)
	fs.Parse(args)

	if *id == "" {
		fatalf("provide --id")
	}
	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/order-requests/"+url.PathEscape(*id), nil, nil)
	if err != nil {
		fatalf("order-requests get failed: %v", err)
	}
	printJSON(resp)
}

func runOrderRequestsCreate(args []string) {
	fs := flag.NewFlagSet("order-requests create", flag.ExitOnError)
	labID := fs.String("lab-id", "", "Lab ID")
	typeID := fs.String("type-id", "", "Type ID")
	name := fs.String("name", "", "Item name")
	vendorName := fs.String("vendor-name", "", "Vendor name")
	catalogNumber := fs.String("catalog-number", "", "Catalog number")
	priceAmount := fs.String("price-amount", "", "Price amount (integer)")
	priceCurrency := fs.String("price-currency", "", "Price currency (e.g., USD)")
	quantity := fs.Int("quantity", 0, "Quantity")
	vendorProductID := fs.String("vendor-product-id", "", "Vendor product ID")
	requiredBefore := fs.String("required-before", "", "Required before (YYYY-MM-DD)")
	notes := fs.String("notes", "", "Notes")
	token := baseFlags(fs)
	fs.Parse(args)

	labValue := envOrFlag(*labID, "QUARTZY_LAB_ID")
	if labValue == "" || *typeID == "" || *name == "" || *vendorName == "" || *catalogNumber == "" || *priceAmount == "" || *priceCurrency == "" || *quantity <= 0 {
		fatalf("provide --lab-id, --type-id, --name, --vendor-name, --catalog-number, --price-amount, --price-currency, and --quantity")
	}

	body := map[string]interface{}{
		"lab_id":         labValue,
		"type_id":        *typeID,
		"name":           *name,
		"vendor_name":    *vendorName,
		"catalog_number": *catalogNumber,
		"price": map[string]string{
			"amount":   *priceAmount,
			"currency": *priceCurrency,
		},
		"quantity": *quantity,
	}
	if *vendorProductID != "" {
		body["vendor_product_id"] = *vendorProductID
	}
	if *requiredBefore != "" {
		body["required_before"] = *requiredBefore
	}
	if *notes != "" {
		body["notes"] = *notes
	}

	c := newClient(*token, true)
	resp, err := c.doRequest("POST", "/order-requests", nil, body)
	if err != nil {
		fatalf("order-requests create failed: %v", err)
	}
	printJSON(resp)
}

func runOrderRequestsUpdate(args []string) {
	fs := flag.NewFlagSet("order-requests update", flag.ExitOnError)
	id := fs.String("id", "", "Order request ID")
	status := fs.String("status", "", "Status")
	token := baseFlags(fs)
	fs.Parse(args)

	if *id == "" || *status == "" {
		fatalf("provide --id and --status")
	}
	if !isValidOrderStatus(*status) {
		fatalf("invalid --status: %s", *status)
	}

	body := map[string]string{
		"status": *status,
	}
	c := newClient(*token, true)
	resp, err := c.doRequest("PUT", "/order-requests/"+url.PathEscape(*id), nil, body)
	if err != nil {
		fatalf("order-requests update failed: %v", err)
	}
	printJSON(resp)
}

func runTypes(args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		runTypesList(args[1:])
	default:
		usage()
		os.Exit(1)
	}
}

func runTypesList(args []string) {
	fs := flag.NewFlagSet("types list", flag.ExitOnError)
	labID := fs.String("lab-id", "", "Lab ID")
	name := fs.String("name", "", "Type name")
	page := fs.Int("page", 0, "Page number")
	token := baseFlags(fs)
	fs.Parse(args)

	query := url.Values{}
	labValue := envOrFlag(*labID, "QUARTZY_LAB_ID")
	if labValue != "" {
		query.Set("lab_id", labValue)
	}
	if *name != "" {
		query.Set("name", *name)
	}
	if *page > 0 {
		query.Set("page", fmt.Sprintf("%d", *page))
	}

	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/types", query, nil)
	if err != nil {
		fatalf("types list failed: %v", err)
	}
	printJSON(resp)
}

func runWebhooks(args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		runWebhooksList(args[1:])
	case "get":
		runWebhooksGet(args[1:])
	case "create":
		runWebhooksCreate(args[1:])
	case "update":
		runWebhooksUpdate(args[1:])
	default:
		usage()
		os.Exit(1)
	}
}

func runWebhooksList(args []string) {
	fs := flag.NewFlagSet("webhooks list", flag.ExitOnError)
	orgID := fs.String("organization-id", "", "Organization ID")
	page := fs.Int("page", 0, "Page number")
	token := baseFlags(fs)
	fs.Parse(args)

	query := url.Values{}
	orgValue := envOrFlag(*orgID, "QUARTZY_ORGANIZATION_ID")
	if orgValue != "" {
		query.Set("organization_id", orgValue)
	}
	if *page > 0 {
		query.Set("page", fmt.Sprintf("%d", *page))
	}

	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/webhooks", query, nil)
	if err != nil {
		fatalf("webhooks list failed: %v", err)
	}
	printJSON(resp)
}

func runWebhooksGet(args []string) {
	fs := flag.NewFlagSet("webhooks get", flag.ExitOnError)
	id := fs.String("id", "", "Webhook ID")
	token := baseFlags(fs)
	fs.Parse(args)

	if *id == "" {
		fatalf("provide --id")
	}
	c := newClient(*token, true)
	resp, err := c.doRequest("GET", "/webhooks/"+url.PathEscape(*id), nil, nil)
	if err != nil {
		fatalf("webhooks get failed: %v", err)
	}
	printJSON(resp)
}

func runWebhooksCreate(args []string) {
	fs := flag.NewFlagSet("webhooks create", flag.ExitOnError)
	urlValue := fs.String("url", "", "Webhook URL")
	labID := fs.String("lab-id", "", "Lab ID")
	orgID := fs.String("organization-id", "", "Organization ID")
	name := fs.String("name", "", "Webhook name")
	eventTypes := fs.String("event-types", "", "Comma-separated event types")
	isEnabled := fs.String("is-enabled", "", "true|false")
	isVerified := fs.String("is-verified", "", "true|false")
	isSigned := fs.String("is-signed", "", "true|false")
	token := baseFlags(fs)
	fs.Parse(args)

	if *urlValue == "" {
		fatalf("provide --url")
	}
	labValue := envOrFlag(*labID, "QUARTZY_LAB_ID")
	orgValue := envOrFlag(*orgID, "QUARTZY_ORGANIZATION_ID")
	if labValue != "" && orgValue != "" {
		fatalf("provide exactly one of --lab-id or --organization-id (both set in env)")
	}
	if labValue == "" && orgValue == "" {
		fatalf("provide --lab-id or --organization-id (or set QUARTZY_LAB_ID or QUARTZY_ORGANIZATION_ID)")
	}

	body := map[string]interface{}{
		"url": *urlValue,
	}
	if labValue != "" {
		body["lab_id"] = labValue
	}
	if orgValue != "" {
		body["organization_id"] = orgValue
	}
	if *name != "" {
		body["name"] = *name
	}
	if *eventTypes != "" {
		body["event_types"] = splitCSV(*eventTypes)
	}
	if val, ok, err := parseOptionalBool(*isEnabled); err != nil {
		fatalf("invalid --is-enabled: %v", err)
	} else if ok {
		body["is_enabled"] = val
	}
	if val, ok, err := parseOptionalBool(*isVerified); err != nil {
		fatalf("invalid --is-verified: %v", err)
	} else if ok {
		body["is_verified"] = val
	}
	if val, ok, err := parseOptionalBool(*isSigned); err != nil {
		fatalf("invalid --is-signed: %v", err)
	} else if ok {
		body["is_signed"] = val
	}

	c := newClient(*token, true)
	resp, err := c.doRequest("POST", "/webhooks", nil, body)
	if err != nil {
		fatalf("webhooks create failed: %v", err)
	}
	printJSON(resp)
}

func runWebhooksUpdate(args []string) {
	fs := flag.NewFlagSet("webhooks update", flag.ExitOnError)
	id := fs.String("id", "", "Webhook ID")
	isEnabled := fs.String("is-enabled", "", "true|false")
	token := baseFlags(fs)
	fs.Parse(args)

	if *id == "" || *isEnabled == "" {
		fatalf("provide --id and --is-enabled")
	}

	val, ok, err := parseOptionalBool(*isEnabled)
	if err != nil || !ok {
		fatalf("invalid --is-enabled: %v", err)
	}

	body := map[string]bool{
		"is_enabled": val,
	}
	c := newClient(*token, true)
	resp, err := c.doRequest("PUT", "/webhooks/"+url.PathEscape(*id), nil, body)
	if err != nil {
		fatalf("webhooks update failed: %v", err)
	}
	printJSON(resp)
}

func baseFlags(fs *flag.FlagSet) *string {
	return fs.String("token", "", "Access token (overrides QUARTZY_KEY)")
}

func newClient(tokenOverride string, requireToken bool) *client {
	token := tokenOverride
	if token == "" {
		token = os.Getenv("QUARTZY_KEY")
	}
	if requireToken && token == "" {
		fatalf("missing access token; set QUARTZY_KEY in .env or pass --token")
	}
	return &client{
		baseURL: envOrDefault("QUARTZY_BASE_URL", defaultBaseURL),
		token:   token,
		http: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (c *client) doRequest(method, path string, query url.Values, body interface{}) ([]byte, error) {
	fullURL := strings.TrimRight(c.baseURL, "/") + path
	if len(query) > 0 {
		fullURL += "?" + query.Encode()
	}

	var payload io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		payload = bytes.NewReader(data)
	}

	req, err := http.NewRequest(method, fullURL, payload)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	if c.token != "" {
		req.Header.Set("Access-Token", c.token)
	}
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
		return nil, fmt.Errorf("quartzy api error (%d): %s", resp.StatusCode, strings.TrimSpace(string(respBody)))
	}
	return respBody, nil
}

func printJSON(data []byte) {
	if len(bytes.TrimSpace(data)) == 0 {
		return
	}
	var out bytes.Buffer
	if err := json.Indent(&out, data, "", "  "); err == nil {
		fmt.Println(out.String())
		return
	}
	fmt.Println(string(data))
}

func parseOptionalBool(val string) (bool, bool, error) {
	val = strings.TrimSpace(strings.ToLower(val))
	if val == "" {
		return false, false, nil
	}
	switch val {
	case "true", "t", "1", "yes", "y":
		return true, true, nil
	case "false", "f", "0", "no", "n":
		return false, true, nil
	default:
		return false, false, fmt.Errorf("expected true or false")
	}
}

func splitCSV(val string) []string {
	raw := strings.Split(val, ",")
	out := make([]string, 0, len(raw))
	for _, item := range raw {
		item = strings.TrimSpace(item)
		if item == "" {
			continue
		}
		out = append(out, item)
	}
	return out
}

func isValidOrderStatus(status string) bool {
	switch status {
	case "PENDING", "CREATED", "CANCELLED", "APPROVED", "ORDERED", "BACKORDERED", "RECEIVED":
		return true
	default:
		return false
	}
}

func filterOrderRequests(data []byte, statuses []string) ([]byte, error) {
	var raw []map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, err
	}
	allowed := make(map[string]struct{}, len(statuses))
	for _, status := range statuses {
		allowed[status] = struct{}{}
	}
	filtered := make([]map[string]interface{}, 0, len(raw))
	for _, item := range raw {
		val, ok := item["status"]
		if !ok {
			continue
		}
		status, ok := val.(string)
		if !ok {
			continue
		}
		if _, ok := allowed[status]; ok {
			filtered = append(filtered, item)
		}
	}
	return json.Marshal(filtered)
}

func fatalf(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
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

func envOrDefault(key, def string) string {
	val := os.Getenv(key)
	if val == "" {
		return def
	}
	return val
}

func envOrFlag(flagValue, envKey string) string {
	if flagValue != "" {
		return flagValue
	}
	return os.Getenv(envKey)
}
