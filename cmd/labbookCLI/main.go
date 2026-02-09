package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type client struct {
	baseURL string
	apiKey  string
	token   string
}

type registryCreatePayload struct {
	Name        string                 `json:"name"`
	Kind        string                 `json:"kind"`
	Description *string                `json:"description,omitempty"`
	Metadata    map[string]interface{} `json:"metadata,omitempty"`
}

type entryPayload struct {
	Title         string                 `json:"title"`
	Project       *string                `json:"project,omitempty"`
	Tags          []string               `json:"tags"`
	ContentHTML   string                 `json:"contentHtml"`
	Widgets       interface{}            `json:"widgets,omitempty"`
	Metadata      map[string]interface{} `json:"metadata,omitempty"`
	RegistryLinks []entryRegistryLink    `json:"registryLinks,omitempty"`
	AgentID       *string                `json:"agentId,omitempty"`
}

type entryAppendPayload struct {
	AppendHTML string  `json:"appendHtml"`
	AgentID    *string `json:"agentId,omitempty"`
}

type entryItem struct {
	ID       int                    `json:"id"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}

type entryRegistryLink struct {
	RegistryID int                    `json:"registryId"`
	LinkType   string                 `json:"linkType"`
	Details    map[string]interface{} `json:"details,omitempty"`
}

type templatePayload struct {
	Name        string `json:"name"`
	ContentHTML string `json:"contentHtml"`
}

type sharePayload struct {
	UserEmail  string `json:"userEmail"`
	Permission string `json:"permission"`
}

type registryItem struct {
	ID          int                    `json:"id"`
	Name        string                 `json:"name"`
	Kind        string                 `json:"kind"`
	Description *string                `json:"description,omitempty"`
	Metadata    map[string]interface{} `json:"metadata,omitempty"`
	CreatedAt   string                 `json:"createdAt"`
}

type registryPatchPayload struct {
	Name        *string                `json:"name,omitempty"`
	Kind        *string                `json:"kind,omitempty"`
	Description *string                `json:"description,omitempty"`
	Metadata    map[string]interface{} `json:"metadata,omitempty"`
}

type attachment struct {
	ID       int    `json:"id"`
	FileName string `json:"fileName"`
	FileUrl  string `json:"fileUrl"`
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}

	baseURL := getEnvOrDefault("LABBOOK_BASE_URL", "http://localhost:4000")
	apiKey := os.Getenv("LABBOOK_API_KEY")
	token := os.Getenv("LABBOOK_TOKEN")

	rootFlags := flag.NewFlagSet("labbookCLI", flag.ExitOnError)
	rootBaseURL := rootFlags.String("base-url", baseURL, "API base URL")
	rootAPIKey := rootFlags.String("api-key", apiKey, "API key (Bearer)")
	rootToken := rootFlags.String("token", token, "Bearer token (JWT)")
	_ = rootFlags.Parse(os.Args[1:2])

	cmd := os.Args[1]
	c := client{baseURL: normalizeBaseURL(*rootBaseURL), apiKey: *rootAPIKey, token: *rootToken}

	switch cmd {
	case "health":
		healthCmd(c)
	case "auth":
		authCmd(c, os.Args[2:])
	case "registry":
		registryCmd(c, os.Args[2:])
	case "entries":
		entriesCmd(c, os.Args[2:])
	case "templates":
		templatesCmd(c, os.Args[2:])
	case "uploads":
		uploadsCmd(c, os.Args[2:])
	case "audit":
		auditCmd(c, os.Args[2:])
	case "api-keys":
		apiKeysCmd(c, os.Args[2:])
	case "widgets":
		widgetsCmd(c, os.Args[2:])
	default:
		usage()
		os.Exit(1)
	}
}

func usage() {
	fmt.Println("labbookCLI <command> [args]")
	fmt.Println("Global flags:")
	fmt.Println("  --base-url --api-key --token")
	fmt.Println("Commands:")
	fmt.Println("  health")
	fmt.Println("  auth login --email --password")
	fmt.Println("  auth me")
	fmt.Println("  auth register --email --name --initials --password")
	fmt.Println("  registry list [--q] [--kind] [--limit] [--offset] [--show-total]")
	fmt.Println("  registry list [--used-in-entry] [--produced-by-entry] [--include-entry-links]")
	fmt.Println("  registry get --id [--show-entries]")
	fmt.Println("  registry create --name --kind [--description] [--plasmid-id] [--insert] [--backbone] [--resistance] [--status] [--location] [--primers] [--concentration] [--sequenced] [--sequence-aa] [--comments]")
	fmt.Println("  registry update --id [--name] [--kind] [--description] [--plasmid-id] [--insert] [--backbone] [--resistance] [--status] [--location] [--primers] [--concentration] [--sequenced] [--sequence-aa] [--comments] [--merge]")
	fmt.Println("  registry create --name --kind \"Protein preparation\" [--aliquot-label] [--concentration-mg-ml] [--concentration-um] [--a260-a280] [--molecular-weight-da] [--molar-extinction-coeff] [--storage-buffer] [--aliquot-size-ul] [--plasmid-ref-id] [--expression-system] [--species] [--available] [--prepped-by] [--prepped-on] [--aliquot-count] [--location]")
	fmt.Println("  registry create --name --kind \"Expression\" [--expression-plasmid-id] [--expression-strain] [--virus-id] [--virus-volume] [--start-date] [--harvest-date] [--volume-per-flask] [--media] [--total-volume] [--iptg-mm] [--od-induction] [--temperature] [--induction-time] [--aliquot] [--yfp-harvest] [--purified] [--comment] [--location]")
	fmt.Println("  registry create --name --kind \"Primers\" [--primer-id] [--primer-type] [--primer-sequence] [--primer-length] [--primer-mw] [--primer-gc] [--primer-tm] [--primer-company] [--primer-purification] [--primer-scale] [--primer-yield-ug] [--primer-yield-nmol] [--primer-conc-um] [--primer-conc-ngul] [--primer-comment]")
	fmt.Println("  registry create --name --kind \"Cryo-EM Grid\" [--grid-id] [--grid-project] [--grid-type] [--grid-material] [--grid-mesh] [--grid-hole] [--grid-thickness] [--grid-lot] [--grid-storage] [--grid-status] [--sample-ref-id] [--sample-concentration] [--sample-buffer] [--sample-additives] [--applied-volume-ul] [--blot-time-s] [--blot-force] [--humidity] [--temperature-c] [--plunge-medium] [--glow-discharge] [--ice-quality] [--microscope] [--session-id] [--magnification] [--pixel-size-a] [--defocus-range] [--dose] [--movies-collected] [--screening-notes] [--best-areas] [--issues] [--linked-datasets] [--linked-reports]")
	fmt.Println("  registry update --id ... (same flags as create)")
	fmt.Println("  registry compute-proteins --id [--attachment-id] [--overwrite] [--include-backbone]")
	fmt.Println("  registry update-protein --id --index [--is-target] [--name] [--tag] [--tag-location] [--cleavage-site] [--uniprot-id]")
	fmt.Println("  registry export [--out]")
	fmt.Println("  registry attachments list --id")
	fmt.Println("  registry attachments upload --id --file")
	fmt.Println("  registry attachments delete --id --attachment-id")
	fmt.Println("  registry attachments download --id --attachment-id [--out]")
	fmt.Println("  entries list [--q] [--project] [--tag] [--from] [--to]")
	fmt.Println("  entries list [--uses-registry] [--produces-registry]")
	fmt.Println("  entries get --id")
	fmt.Println("  entries create --title --content-html [--project] [--tags] [--content-file] [--widgets] [--widgets-file] [--metadata] [--metadata-file] [--uses] [--produces] [--registry-links] [--registry-links-file] [--agent-id]")
	fmt.Println("  entries update --id --title --content-html [--project] [--tags] [--content-file] [--widgets] [--widgets-file] [--metadata] [--metadata-file] [--merge-metadata] [--uses] [--produces] [--registry-links] [--registry-links-file] [--agent-id]")
	fmt.Println("  entries append --id --append-html [--append-file] [--agent-id]")
	fmt.Println("  entries delete --id")
	fmt.Println("  entries links --id")
	fmt.Println("  entries link --entry-id --registry-id --type [--details]")
	fmt.Println("  entries unlink --entry-id --link-id")
	fmt.Println("  entries lock --id")
	fmt.Println("  entries unlock --id")
	fmt.Println("  entries versions --id")
	fmt.Println("  entries restore --id --version-id")
	fmt.Println("  entries export-html --id [--out]")
	fmt.Println("  entries shares list --id")
	fmt.Println("  entries shares add --id --user-email --permission")
	fmt.Println("  entries shares delete --id --share-id")
	fmt.Println("  entries attachments list --id")
	fmt.Println("  entries attachments upload --id --file")
	fmt.Println("  entries attachments delete --id --attachment-id")
	fmt.Println("  entries attachments download --id --attachment-id [--out]")
	fmt.Println("  templates list")
	fmt.Println("  templates create --name --content-html [--content-file]")
	fmt.Println("  templates shares list --id")
	fmt.Println("  templates shares add --id --user-email --permission")
	fmt.Println("  templates shares delete --id --share-id")
	fmt.Println("  templates render --id [--vars] [--vars-file] [--out] [--out-widgets]")
	fmt.Println("  uploads upload --file")
	fmt.Println("  audit list [--limit]")
	fmt.Println("  api-keys create --name --user-email --scopes")
	fmt.Println("  widgets types")
	fmt.Println("  widgets compute --widgets [--widgets-file]")
	fmt.Println("Environment:")
	fmt.Println("  LABBOOK_BASE_URL, LABBOOK_API_KEY, LABBOOK_TOKEN")
}

func healthCmd(c client) {
	body, err := c.requestNoAuth("GET", "/api/health", nil)
	exitOnError(err)
	fmt.Println(string(body))
}

func authCmd(c client, args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "login":
		fs := flag.NewFlagSet("auth login", flag.ExitOnError)
		email := fs.String("email", "", "Email")
		password := fs.String("password", "", "Password")
		_ = fs.Parse(args[1:])
		if strings.TrimSpace(*email) == "" || strings.TrimSpace(*password) == "" {
			exitOnError(errors.New("email and password are required"))
		}
		payload := map[string]string{"email": *email, "password": *password}
		body, err := c.requestNoAuth("POST", "/api/auth/login", payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "me":
		exitOnError(ensureToken(c))
		body, err := c.request("GET", "/api/me", nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "register":
		exitOnError(ensureToken(c))
		fs := flag.NewFlagSet("auth register", flag.ExitOnError)
		email := fs.String("email", "", "Email")
		name := fs.String("name", "", "Name")
		initials := fs.String("initials", "", "Initials")
		password := fs.String("password", "", "Password")
		_ = fs.Parse(args[1:])
		if strings.TrimSpace(*email) == "" || strings.TrimSpace(*name) == "" ||
			strings.TrimSpace(*initials) == "" || strings.TrimSpace(*password) == "" {
			exitOnError(errors.New("email, name, initials, and password are required"))
		}
		payload := map[string]string{
			"email":    *email,
			"name":     *name,
			"initials": *initials,
			"password": *password,
		}
		body, err := c.request("POST", "/api/auth/register", payload)
		exitOnError(err)
		fmt.Println(string(body))
	default:
		usage()
		os.Exit(1)
	}
}

func uploadsCmd(c client, args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "upload":
		fs := flag.NewFlagSet("uploads upload", flag.ExitOnError)
		filePath := fs.String("file", "", "Path to file")
		_ = fs.Parse(args[1:])
		if strings.TrimSpace(*filePath) == "" {
			exitOnError(errors.New("file is required"))
		}
		body, err := c.requestUpload("/api/uploads", *filePath)
		exitOnError(err)
		fmt.Println(string(body))
	default:
		usage()
		os.Exit(1)
	}
}

func registryCmd(c client, args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		fs := flag.NewFlagSet("registry list", flag.ExitOnError)
		query := fs.String("q", "", "Search text")
		kind := fs.String("kind", "", "Kind")
		limit := fs.Int("limit", 50, "Page size")
		offset := fs.Int("offset", 0, "Offset")
		showTotal := fs.Bool("show-total", false, "Include total count")
		usedInEntry := fs.Int("used-in-entry", 0, "Entry ID (uses)")
		producedByEntry := fs.Int("produced-by-entry", 0, "Entry ID (produces)")
		includeEntryLinks := fs.Bool("include-entry-links", false, "Include entry links")
		_ = fs.Parse(args[1:])

		params := url.Values{}
		if strings.TrimSpace(*query) != "" {
			params.Set("q", *query)
		}
		if strings.TrimSpace(*kind) != "" {
			params.Set("kind", *kind)
		}
		if *limit > 0 {
			params.Set("limit", fmt.Sprintf("%d", *limit))
		}
		if *offset > 0 {
			params.Set("offset", fmt.Sprintf("%d", *offset))
		}
		if *usedInEntry > 0 {
			params.Set("usedInEntry", fmt.Sprintf("%d", *usedInEntry))
		}
		if *producedByEntry > 0 {
			params.Set("producedByEntry", fmt.Sprintf("%d", *producedByEntry))
		}
		if *includeEntryLinks {
			params.Set("includeEntryLinks", "1")
		}
		path := "/api/registry"
		if encoded := params.Encode(); encoded != "" {
			path += "?" + encoded
		}
		body, err := c.request("GET", path, nil)
		exitOnError(err)
		if *showTotal {
			fmt.Println(string(body))
			return
		}
		var payload struct {
			Items []registryItem `json:"items"`
			Total int            `json:"total"`
		}
		exitOnError(json.Unmarshal(body, &payload))
		data, err := json.Marshal(payload.Items)
		exitOnError(err)
		fmt.Println(string(data))
	case "get":
		fs := flag.NewFlagSet("registry get", flag.ExitOnError)
		id := fs.Int("id", 0, "Registry ID")
		showEntries := fs.Bool("show-entries", false, "Include entry links")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		path := fmt.Sprintf("/api/registry/%d", *id)
		if *showEntries {
			path += "?includeEntryLinks=1"
		}
		body, err := c.request("GET", path, nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "create":
		payload := parseRegistryPayload("registry create", args[1:])
		body, err := c.request("POST", "/api/registry", payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "update":
		id, merge, payload := parseRegistryUpdateArgs(c, args[1:])
		var body []byte
		var err error
		if merge {
			body, err = c.request("PATCH", fmt.Sprintf("/api/registry/%d", id), payload)
		} else {
			body, err = c.request("PUT", fmt.Sprintf("/api/registry/%d", id), payload)
		}
		exitOnError(err)
		fmt.Println(string(body))
	case "compute-proteins":
		fs := flag.NewFlagSet("registry compute-proteins", flag.ExitOnError)
		id := fs.Int("id", 0, "Registry ID (Plasmid)")
		attachmentID := fs.Int("attachment-id", 0, "Specific attachment ID (optional)")
		overwrite := fs.Bool("overwrite", false, "Overwrite existing encodedProteins")
		includeBackbone := fs.Bool("include-backbone", true, "Include backbone genes in result")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		payload := map[string]interface{}{
			"overwrite":       *overwrite,
			"includeBackbone": *includeBackbone,
		}
		if *attachmentID > 0 {
			payload["attachmentId"] = *attachmentID
		}
		body, err := c.request("POST", fmt.Sprintf("/api/registry/%d/compute-proteins", *id), payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "update-protein":
		fs := flag.NewFlagSet("registry update-protein", flag.ExitOnError)
		id := fs.Int("id", 0, "Registry ID")
		index := fs.Int("index", -1, "Protein index")
		isTarget := fs.String("is-target", "", "Set target classification (true/false)")
		name := fs.String("name", "", "Protein name")
		tag := fs.String("tag", "", "Tag type")
		tagLocation := fs.String("tag-location", "", "Tag location (N/C)")
		cleavageSite := fs.String("cleavage-site", "", "Cleavage site")
		uniprotID := fs.String("uniprot-id", "", "UniProt ID")
		_ = fs.Parse(args[1:])
		if *id == 0 || *index < 0 {
			exitOnError(errors.New("id and index are required"))
		}
		payload := map[string]interface{}{}
		if *isTarget != "" {
			payload["isTarget"] = *isTarget == "true"
		}
		if *name != "" {
			payload["name"] = *name
		}
		if *tag != "" {
			payload["tag"] = *tag
		}
		if *tagLocation != "" {
			payload["tagLocation"] = *tagLocation
		}
		if *cleavageSite != "" {
			payload["cleavageSite"] = *cleavageSite
		}
		if *uniprotID != "" {
			payload["uniprotId"] = *uniprotID
		}
		body, err := c.request("PATCH", fmt.Sprintf("/api/registry/%d/proteins/%d", *id, *index), payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "export":
		fs := flag.NewFlagSet("registry export", flag.ExitOnError)
		out := fs.String("out", "", "Write output to file")
		_ = fs.Parse(args[1:])
		body, err := c.request("GET", "/api/registry/export/csv", nil)
		exitOnError(err)
		exitOnError(writeOutput(*out, body))
	case "attachments":
		if len(args) < 2 {
			usage()
			os.Exit(1)
		}
		switch args[1] {
		case "list":
			fs := flag.NewFlagSet("registry attachments list", flag.ExitOnError)
			id := fs.Int("id", 0, "Registry ID")
			_ = fs.Parse(args[2:])
			if *id == 0 {
				exitOnError(errors.New("id is required"))
			}
			body, err := c.request("GET", fmt.Sprintf("/api/registry/%d/attachments", *id), nil)
			exitOnError(err)
			fmt.Println(string(body))
		case "upload":
			fs := flag.NewFlagSet("registry attachments upload", flag.ExitOnError)
			id := fs.Int("id", 0, "Registry ID")
			filePath := fs.String("file", "", "Path to file")
			_ = fs.Parse(args[2:])
			if *id == 0 || strings.TrimSpace(*filePath) == "" {
				exitOnError(errors.New("id and file are required"))
			}
			body, err := c.requestUpload(fmt.Sprintf("/api/registry/%d/attachments", *id), *filePath)
			exitOnError(err)
			fmt.Println(string(body))
		case "delete":
			fs := flag.NewFlagSet("registry attachments delete", flag.ExitOnError)
			id := fs.Int("id", 0, "Registry ID")
			attachmentID := fs.Int("attachment-id", 0, "Attachment ID")
			_ = fs.Parse(args[2:])
			if *id == 0 || *attachmentID == 0 {
				exitOnError(errors.New("id and attachment-id are required"))
			}
			body, err := c.request("DELETE", fmt.Sprintf("/api/registry/%d/attachments/%d", *id, *attachmentID), nil)
			exitOnError(err)
			fmt.Println(string(body))
		case "download":
			fs := flag.NewFlagSet("registry attachments download", flag.ExitOnError)
			id := fs.Int("id", 0, "Registry ID")
			attachmentID := fs.Int("attachment-id", 0, "Attachment ID")
			out := fs.String("out", "", "Write output to file")
			_ = fs.Parse(args[2:])
			if *id == 0 || *attachmentID == 0 {
				exitOnError(errors.New("id and attachment-id are required"))
			}
			fileURL, fileName := fetchAttachmentURL(c, fmt.Sprintf("/api/registry/%d/attachments", *id), *attachmentID)
			downloadPath := *out
			if strings.TrimSpace(downloadPath) == "" {
				downloadPath = fileName
			}
			exitOnError(downloadFile(c.baseURL, fileURL, downloadPath))
		default:
			usage()
			os.Exit(1)
		}
	default:
		usage()
		os.Exit(1)
	}
}

func parseRegistryUpdateArgs(c client, args []string) (int, bool, interface{}) {
	// Scan for --id and --merge manually since the full FlagSet is in the downstream functions
	id, merge := scanIDAndMerge(args)
	if id == 0 {
		exitOnError(errors.New("id is required"))
	}
	var existing *registryItem
	if merge {
		item, err := fetchRegistryByID(c, id)
		if err != nil {
			exitOnError(err)
		}
		existing = &item
	}
	if merge {
		_, patch := parseRegistryPatchPayloadWithID("registry update", stripMergeFlag(args), existing)
		return id, true, patch
	}
	_, full := parseRegistryPayloadWithID("registry update", stripMergeFlag(args))
	return id, false, full
}

func scanIDAndMerge(args []string) (int, bool) {
	id := 0
	merge := false
	for i := 0; i < len(args); i++ {
		arg := args[i]
		if arg == "--merge" || arg == "-merge" {
			merge = true
		} else if strings.HasPrefix(arg, "--merge=") || strings.HasPrefix(arg, "-merge=") {
			val := strings.TrimPrefix(strings.TrimPrefix(arg, "--merge="), "-merge=")
			merge = val == "true" || val == "1"
		} else if arg == "--id" || arg == "-id" {
			if i+1 < len(args) {
				if v, err := strconv.Atoi(args[i+1]); err == nil {
					id = v
				}
				i++
			}
		} else if strings.HasPrefix(arg, "--id=") || strings.HasPrefix(arg, "-id=") {
			val := strings.TrimPrefix(strings.TrimPrefix(arg, "--id="), "-id=")
			if v, err := strconv.Atoi(val); err == nil {
				id = v
			}
		}
	}
	return id, merge
}

func stripMergeFlag(args []string) []string {
	out := make([]string, 0, len(args))
	skipNext := false
	for _, arg := range args {
		if skipNext {
			skipNext = false
			continue
		}
		if arg == "--merge" || arg == "-merge" {
			continue
		}
		if strings.HasPrefix(arg, "--merge=") || strings.HasPrefix(arg, "-merge=") {
			continue
		}
		out = append(out, arg)
	}
	return out
}

func entriesCmd(c client, args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		fs := flag.NewFlagSet("entries list", flag.ExitOnError)
		query := fs.String("q", "", "Search text")
		project := fs.String("project", "", "Project")
		tag := fs.String("tag", "", "Tag (comma-separated)")
		from := fs.String("from", "", "From date (YYYY-MM-DD)")
		to := fs.String("to", "", "To date (YYYY-MM-DD)")
		usesRegistry := fs.Int("uses-registry", 0, "Registry ID (uses)")
		producesRegistry := fs.Int("produces-registry", 0, "Registry ID (produces)")
		_ = fs.Parse(args[1:])

		queryParams := make([]string, 0)
		if strings.TrimSpace(*query) != "" {
			queryParams = append(queryParams, "q="+url.QueryEscape(*query))
		}
		if strings.TrimSpace(*project) != "" {
			queryParams = append(queryParams, "project="+url.QueryEscape(*project))
		}
		if strings.TrimSpace(*tag) != "" {
			queryParams = append(queryParams, "tag="+url.QueryEscape(*tag))
		}
		if strings.TrimSpace(*from) != "" {
			queryParams = append(queryParams, "from="+url.QueryEscape(*from))
		}
		if strings.TrimSpace(*to) != "" {
			queryParams = append(queryParams, "to="+url.QueryEscape(*to))
		}
		if *usesRegistry > 0 {
			queryParams = append(queryParams, fmt.Sprintf("usesRegistry=%d", *usesRegistry))
		}
		if *producesRegistry > 0 {
			queryParams = append(queryParams, fmt.Sprintf("producesRegistry=%d", *producesRegistry))
		}
		path := "/api/entries"
		if len(queryParams) > 0 {
			path += "?" + strings.Join(queryParams, "&")
		}
		body, err := c.request("GET", path, nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "get":
		fs := flag.NewFlagSet("entries get", flag.ExitOnError)
		id := fs.Int("id", 0, "Entry ID")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		body, err := c.request("GET", fmt.Sprintf("/api/entries/%d", *id), nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "create":
		payload, _ := parseEntryPayload("entries create", args[1:])
		body, err := c.request("POST", "/api/entries", payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "update":
		id, payload, metadataProvided, mergeMetadataFlag := parseEntryPayloadWithID("entries update", args[1:])
		if id == 0 {
			exitOnError(errors.New("id is required"))
		}
		if mergeMetadataFlag && !metadataProvided {
			exitOnError(errors.New("merge-metadata requires metadata input"))
		}
		if metadataProvided && mergeMetadataFlag {
			existing, err := fetchEntryByID(c, id)
			exitOnError(err)
			payload.Metadata = mergeMetadata(existing.Metadata, payload.Metadata)
		}
		body, err := c.request("PUT", fmt.Sprintf("/api/entries/%d", id), payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "append":
		id, payload := parseEntryAppendPayload("entries append", args[1:])
		if id == 0 {
			exitOnError(errors.New("id is required"))
		}
		body, err := c.request("POST", fmt.Sprintf("/api/entries/%d/append", id), payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "links":
		fs := flag.NewFlagSet("entries links", flag.ExitOnError)
		id := fs.Int("id", 0, "Entry ID")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		body, err := c.request("GET", fmt.Sprintf("/api/entries/%d/links", *id), nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "link":
		fs := flag.NewFlagSet("entries link", flag.ExitOnError)
		entryID := fs.Int("entry-id", 0, "Entry ID")
		registryID := fs.Int("registry-id", 0, "Registry ID")
		linkType := fs.String("type", "", "uses|produces")
		details := fs.String("details", "", "Details JSON")
		_ = fs.Parse(args[1:])
		if *entryID == 0 || *registryID == 0 || strings.TrimSpace(*linkType) == "" {
			exitOnError(errors.New("entry-id, registry-id, type are required"))
		}
		payload := entryRegistryLink{
			RegistryID: *registryID,
			LinkType:   *linkType,
		}
		if strings.TrimSpace(*details) != "" {
			payload.Details = parseDetailsJSON(*details)
		}
		body, err := c.request("POST", fmt.Sprintf("/api/entries/%d/links", *entryID), payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "unlink":
		fs := flag.NewFlagSet("entries unlink", flag.ExitOnError)
		entryID := fs.Int("entry-id", 0, "Entry ID")
		linkID := fs.Int("link-id", 0, "Link ID")
		_ = fs.Parse(args[1:])
		if *entryID == 0 || *linkID == 0 {
			exitOnError(errors.New("entry-id and link-id are required"))
		}
		body, err := c.request("DELETE", fmt.Sprintf("/api/entries/%d/links/%d", *entryID, *linkID), nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "lock":
		fs := flag.NewFlagSet("entries lock", flag.ExitOnError)
		id := fs.Int("id", 0, "Entry ID")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		body, err := c.request("POST", fmt.Sprintf("/api/entries/%d/lock", *id), nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "unlock":
		fs := flag.NewFlagSet("entries unlock", flag.ExitOnError)
		id := fs.Int("id", 0, "Entry ID")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		body, err := c.request("POST", fmt.Sprintf("/api/entries/%d/unlock", *id), nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "delete":
		fs := flag.NewFlagSet("entries delete", flag.ExitOnError)
		id := fs.Int("id", 0, "Entry ID")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		body, err := c.request("DELETE", fmt.Sprintf("/api/entries/%d", *id), nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "versions":
		fs := flag.NewFlagSet("entries versions", flag.ExitOnError)
		id := fs.Int("id", 0, "Entry ID")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		body, err := c.request("GET", fmt.Sprintf("/api/entries/%d/versions", *id), nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "restore":
		fs := flag.NewFlagSet("entries restore", flag.ExitOnError)
		id := fs.Int("id", 0, "Entry ID")
		versionID := fs.Int("version-id", 0, "Version ID")
		_ = fs.Parse(args[1:])
		if *id == 0 || *versionID == 0 {
			exitOnError(errors.New("id and version-id are required"))
		}
		body, err := c.request("POST", fmt.Sprintf("/api/entries/%d/restore", *id), map[string]int{"versionId": *versionID})
		exitOnError(err)
		fmt.Println(string(body))
	case "export-html":
		fs := flag.NewFlagSet("entries export-html", flag.ExitOnError)
		id := fs.Int("id", 0, "Entry ID")
		out := fs.String("out", "", "Write output to file")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		body, err := c.request("GET", fmt.Sprintf("/api/entries/%d/export/html", *id), nil)
		exitOnError(err)
		exitOnError(writeOutput(*out, body))
	case "shares":
		if len(args) < 2 {
			usage()
			os.Exit(1)
		}
		switch args[1] {
		case "list":
			fs := flag.NewFlagSet("entries shares list", flag.ExitOnError)
			id := fs.Int("id", 0, "Entry ID")
			_ = fs.Parse(args[2:])
			if *id == 0 {
				exitOnError(errors.New("id is required"))
			}
			body, err := c.request("GET", fmt.Sprintf("/api/entries/%d/shares", *id), nil)
			exitOnError(err)
			fmt.Println(string(body))
		case "add":
			fs := flag.NewFlagSet("entries shares add", flag.ExitOnError)
			id := fs.Int("id", 0, "Entry ID")
			userEmail := fs.String("user-email", "", "User email")
			permission := fs.String("permission", "", "read|write")
			_ = fs.Parse(args[2:])
			if *id == 0 || strings.TrimSpace(*userEmail) == "" || strings.TrimSpace(*permission) == "" {
				exitOnError(errors.New("id, user-email, permission are required"))
			}
			payload := sharePayload{UserEmail: *userEmail, Permission: *permission}
			body, err := c.request("POST", fmt.Sprintf("/api/entries/%d/share", *id), payload)
			exitOnError(err)
			fmt.Println(string(body))
		case "delete":
			fs := flag.NewFlagSet("entries shares delete", flag.ExitOnError)
			id := fs.Int("id", 0, "Entry ID")
			shareID := fs.Int("share-id", 0, "Share ID")
			_ = fs.Parse(args[2:])
			if *id == 0 || *shareID == 0 {
				exitOnError(errors.New("id and share-id are required"))
			}
			body, err := c.request("DELETE", fmt.Sprintf("/api/entries/%d/shares/%d", *id, *shareID), nil)
			exitOnError(err)
			fmt.Println(string(body))
		default:
			usage()
			os.Exit(1)
		}
	case "attachments":
		if len(args) < 2 {
			usage()
			os.Exit(1)
		}
		switch args[1] {
		case "list":
			fs := flag.NewFlagSet("entries attachments list", flag.ExitOnError)
			id := fs.Int("id", 0, "Entry ID")
			_ = fs.Parse(args[2:])
			if *id == 0 {
				exitOnError(errors.New("id is required"))
			}
			body, err := c.request("GET", fmt.Sprintf("/api/entries/%d/attachments", *id), nil)
			exitOnError(err)
			fmt.Println(string(body))
		case "upload":
			fs := flag.NewFlagSet("entries attachments upload", flag.ExitOnError)
			id := fs.Int("id", 0, "Entry ID")
			filePath := fs.String("file", "", "Path to file")
			_ = fs.Parse(args[2:])
			if *id == 0 || strings.TrimSpace(*filePath) == "" {
				exitOnError(errors.New("id and file are required"))
			}
			body, err := c.requestUpload(fmt.Sprintf("/api/entries/%d/attachments", *id), *filePath)
			exitOnError(err)
			fmt.Println(string(body))
		case "delete":
			fs := flag.NewFlagSet("entries attachments delete", flag.ExitOnError)
			id := fs.Int("id", 0, "Entry ID")
			attachmentID := fs.Int("attachment-id", 0, "Attachment ID")
			_ = fs.Parse(args[2:])
			if *id == 0 || *attachmentID == 0 {
				exitOnError(errors.New("id and attachment-id are required"))
			}
			body, err := c.request("DELETE", fmt.Sprintf("/api/entries/%d/attachments/%d", *id, *attachmentID), nil)
			exitOnError(err)
			fmt.Println(string(body))
		case "download":
			fs := flag.NewFlagSet("entries attachments download", flag.ExitOnError)
			id := fs.Int("id", 0, "Entry ID")
			attachmentID := fs.Int("attachment-id", 0, "Attachment ID")
			out := fs.String("out", "", "Write output to file")
			_ = fs.Parse(args[2:])
			if *id == 0 || *attachmentID == 0 {
				exitOnError(errors.New("id and attachment-id are required"))
			}
			fileURL, fileName := fetchAttachmentURL(c, fmt.Sprintf("/api/entries/%d/attachments", *id), *attachmentID)
			downloadPath := *out
			if strings.TrimSpace(downloadPath) == "" {
				downloadPath = fileName
			}
			exitOnError(downloadFile(c.baseURL, fileURL, downloadPath))
		default:
			usage()
			os.Exit(1)
		}
	default:
		usage()
		os.Exit(1)
	}
}

func templatesCmd(c client, args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "list":
		body, err := c.request("GET", "/api/templates", nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "create":
		payload := parseTemplatePayload("templates create", args[1:])
		body, err := c.request("POST", "/api/templates", payload)
		exitOnError(err)
		fmt.Println(string(body))
	case "render":
		fs := flag.NewFlagSet("templates render", flag.ExitOnError)
		id := fs.Int("id", 0, "Template ID")
		vars := fs.String("vars", "", "Variables JSON")
		varsFile := fs.String("vars-file", "", "Variables JSON file")
		out := fs.String("out", "", "Write rendered HTML output to file")
		outWidgets := fs.String("out-widgets", "", "Write widgets JSON array to file")
		_ = fs.Parse(args[1:])
		if *id == 0 {
			exitOnError(errors.New("id is required"))
		}
		varMap := parseVars(*vars, *varsFile)
		payload := map[string]interface{}{"variables": varMap}
		body, err := c.request("POST", fmt.Sprintf("/api/templates/%d/render", *id), payload)
		exitOnError(err)

		// Backward compatible behavior: if no output flags are provided, print raw JSON response.
		if strings.TrimSpace(*out) == "" && strings.TrimSpace(*outWidgets) == "" {
			exitOnError(writeOutput("", body))
			break
		}

		type templateRenderResponse struct {
			RenderedHTML string          `json:"renderedHtml"`
			Widgets      json.RawMessage `json:"widgets"`
		}
		var resp templateRenderResponse
		exitOnError(json.Unmarshal(body, &resp))

		// If --out is provided, write HTML there; otherwise print HTML to stdout.
		if strings.TrimSpace(*out) != "" {
			exitOnError(writeOutput(*out, []byte(resp.RenderedHTML)))
		} else {
			exitOnError(writeOutput("", []byte(resp.RenderedHTML)))
		}

		// If --out-widgets is provided, write the widgets array to that file.
		if strings.TrimSpace(*outWidgets) != "" {
			widgetsBytes := bytes.TrimSpace([]byte(resp.Widgets))
			if len(widgetsBytes) == 0 || bytes.Equal(widgetsBytes, []byte("null")) {
				widgetsBytes = []byte("[]")
			}
			var pretty bytes.Buffer
			if err := json.Indent(&pretty, widgetsBytes, "", "  "); err == nil {
				widgetsBytes = pretty.Bytes()
			}
			exitOnError(writeOutput(*outWidgets, widgetsBytes))
		}
	case "shares":
		if len(args) < 2 {
			usage()
			os.Exit(1)
		}
		switch args[1] {
		case "list":
			fs := flag.NewFlagSet("templates shares list", flag.ExitOnError)
			id := fs.Int("id", 0, "Template ID")
			_ = fs.Parse(args[2:])
			if *id == 0 {
				exitOnError(errors.New("id is required"))
			}
			body, err := c.request("GET", fmt.Sprintf("/api/templates/%d/shares", *id), nil)
			exitOnError(err)
			fmt.Println(string(body))
		case "add":
			fs := flag.NewFlagSet("templates shares add", flag.ExitOnError)
			id := fs.Int("id", 0, "Template ID")
			userEmail := fs.String("user-email", "", "User email")
			permission := fs.String("permission", "", "read|write")
			_ = fs.Parse(args[2:])
			if *id == 0 || strings.TrimSpace(*userEmail) == "" || strings.TrimSpace(*permission) == "" {
				exitOnError(errors.New("id, user-email, permission are required"))
			}
			payload := sharePayload{UserEmail: *userEmail, Permission: *permission}
			body, err := c.request("POST", fmt.Sprintf("/api/templates/%d/share", *id), payload)
			exitOnError(err)
			fmt.Println(string(body))
		case "delete":
			fs := flag.NewFlagSet("templates shares delete", flag.ExitOnError)
			id := fs.Int("id", 0, "Template ID")
			shareID := fs.Int("share-id", 0, "Share ID")
			_ = fs.Parse(args[2:])
			if *id == 0 || *shareID == 0 {
				exitOnError(errors.New("id and share-id are required"))
			}
			body, err := c.request("DELETE", fmt.Sprintf("/api/templates/%d/shares/%d", *id, *shareID), nil)
			exitOnError(err)
			fmt.Println(string(body))
		default:
			usage()
			os.Exit(1)
		}
	default:
		usage()
		os.Exit(1)
	}
}

func auditCmd(c client, args []string) {
	exitOnError(ensureToken(c))
	fs := flag.NewFlagSet("audit list", flag.ExitOnError)
	limit := fs.Int("limit", 50, "Number of entries")
	_ = fs.Parse(args)
	path := fmt.Sprintf("/api/audit?limit=%d", *limit)
	body, err := c.request("GET", path, nil)
	exitOnError(err)
	fmt.Println(string(body))
}

func apiKeysCmd(c client, args []string) {
	exitOnError(ensureToken(c))
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "create":
		fs := flag.NewFlagSet("api-keys create", flag.ExitOnError)
		name := fs.String("name", "", "Name")
		userEmail := fs.String("user-email", "", "User email")
		scopes := fs.String("scopes", "", "Comma-separated scopes")
		_ = fs.Parse(args[1:])
		if strings.TrimSpace(*name) == "" || strings.TrimSpace(*userEmail) == "" || strings.TrimSpace(*scopes) == "" {
			exitOnError(errors.New("name, user-email, scopes are required"))
		}
		payload := map[string]interface{}{
			"name":      *name,
			"userEmail": *userEmail,
			"scopes":    splitTags(*scopes),
		}
		body, err := c.request("POST", "/api/api-keys", payload)
		exitOnError(err)
		fmt.Println(string(body))
	default:
		usage()
		os.Exit(1)
	}
}

func widgetsCmd(c client, args []string) {
	if len(args) < 1 {
		usage()
		os.Exit(1)
	}
	switch args[0] {
	case "types":
		body, err := c.request("GET", "/api/widgets/types", nil)
		exitOnError(err)
		fmt.Println(string(body))
	case "compute":
		fs := flag.NewFlagSet("widgets compute", flag.ExitOnError)
		widgets := fs.String("widgets", "", "Widgets JSON array")
		widgetsFile := fs.String("widgets-file", "", "Path to widgets JSON file")
		_ = fs.Parse(args[1:])

		var widgetsData interface{}
		if strings.TrimSpace(*widgetsFile) != "" {
			data, err := os.ReadFile(*widgetsFile)
			exitOnError(err)
			err = json.Unmarshal(data, &widgetsData)
			exitOnError(err)
		} else if strings.TrimSpace(*widgets) != "" {
			err := json.Unmarshal([]byte(*widgets), &widgetsData)
			exitOnError(err)
		} else {
			exitOnError(errors.New("widgets or widgets-file is required"))
		}

		payload := map[string]interface{}{"widgets": widgetsData}
		body, err := c.request("POST", "/api/widgets/compute", payload)
		exitOnError(err)
		fmt.Println(string(body))
	default:
		usage()
		os.Exit(1)
	}
}

func parseEntryAppendPayload(name string, args []string) (int, entryAppendPayload) {
	fs := flag.NewFlagSet(name, flag.ExitOnError)
	id := fs.Int("id", 0, "Entry ID")
	appendHTML := fs.String("append-html", "", "HTML content to append")
	appendFile := fs.String("append-file", "", "Path to HTML file to append")
	agentID := fs.String("agent-id", "", "Agent identifier")
	_ = fs.Parse(args)

	content := strings.TrimSpace(*appendHTML)
	if content == "" && strings.TrimSpace(*appendFile) != "" {
		data, err := os.ReadFile(*appendFile)
		exitOnError(err)
		content = string(data)
	}
	if strings.TrimSpace(content) == "" {
		exitOnError(errors.New("append-html or append-file is required"))
	}

	payload := entryAppendPayload{
		AppendHTML: content,
	}
	if strings.TrimSpace(*agentID) != "" {
		payload.AgentID = agentID
	}

	return *id, payload
}

func parseEntryPayload(name string, args []string) (entryPayload, bool) {
	id, payload, metadataProvided, _ := parseEntryPayloadWithID(name, args)
	_ = id // ignore id for create
	return payload, metadataProvided
}

func parseEntryPayloadWithID(name string, args []string) (int, entryPayload, bool, bool) {
	fs := flag.NewFlagSet(name, flag.ExitOnError)
	id := fs.Int("id", 0, "Entry ID")
	title := fs.String("title", "", "Title")
	project := fs.String("project", "", "Project")
	tags := fs.String("tags", "", "Comma-separated tags")
	contentHTML := fs.String("content-html", "", "HTML content")
	contentFile := fs.String("content-file", "", "Path to HTML file")
	widgetsFlag := fs.String("widgets", "", "Widgets JSON array")
	widgetsFile := fs.String("widgets-file", "", "Path to widgets JSON file")
	metadataFlag := fs.String("metadata", "", "Metadata JSON string")
	metadataFile := fs.String("metadata-file", "", "Path to metadata JSON file")
	mergeMetadata := fs.Bool("merge-metadata", false, "Merge metadata with existing entry (update only)")
	registryLinksFlag := fs.String("registry-links", "", "Registry links JSON array")
	registryLinksFile := fs.String("registry-links-file", "", "Path to registry links JSON file")
	uses := stringList{}
	produces := stringList{}
	agentID := fs.String("agent-id", "", "Agent identifier")
	fs.Var(&uses, "uses", "Registry usage link (e.g. 28:volume_ul=4)")
	fs.Var(&produces, "produces", "Registry produced link (e.g. 106:yield_mg=2.5)")
	_ = fs.Parse(args)

	if strings.TrimSpace(*title) == "" {
		exitOnError(errors.New("title is required"))
	}

	content := strings.TrimSpace(*contentHTML)
	if content == "" && strings.TrimSpace(*contentFile) != "" {
		data, err := os.ReadFile(*contentFile)
		exitOnError(err)
		content = string(data)
	}
	if content == "" {
		exitOnError(errors.New("content-html or content-file is required"))
	}

	payload := entryPayload{
		Title:       *title,
		ContentHTML: content,
		Tags:        splitTags(*tags),
	}
	if strings.TrimSpace(*project) != "" {
		payload.Project = project
	}
	widgetsProvided := strings.TrimSpace(*widgetsFlag) != "" || strings.TrimSpace(*widgetsFile) != ""
	if widgetsProvided {
		payload.Widgets = parseWidgetsArrayPayload(*widgetsFlag, *widgetsFile)
	}
	metadataProvided := strings.TrimSpace(*metadataFlag) != "" || strings.TrimSpace(*metadataFile) != ""
	if metadataProvided {
		payload.Metadata = parseMetadataPayload(*metadataFlag, *metadataFile)
	}
	if strings.TrimSpace(*registryLinksFlag) != "" || strings.TrimSpace(*registryLinksFile) != "" {
		payload.RegistryLinks = parseRegistryLinksPayload(*registryLinksFlag, *registryLinksFile)
	}
	if len(uses) > 0 {
		for _, value := range uses {
			payload.RegistryLinks = append(payload.RegistryLinks, parseRegistryLinkSpec(value, "uses"))
		}
	}
	if len(produces) > 0 {
		for _, value := range produces {
			payload.RegistryLinks = append(payload.RegistryLinks, parseRegistryLinkSpec(value, "produces"))
		}
	}
	if strings.TrimSpace(*agentID) != "" {
		payload.AgentID = agentID
	}
	return *id, payload, metadataProvided, *mergeMetadata
}

func parseRegistryPayload(name string, args []string) registryCreatePayload {
	_, payload := parseRegistryPayloadWithID(name, args)
	return payload
}

func parseRegistryPayloadWithID(name string, args []string) (int, registryCreatePayload) {
	fs := flag.NewFlagSet(name, flag.ExitOnError)
	id := fs.Int("id", 0, "Registry ID")
	nameValue := fs.String("name", "", "Name")
	kind := fs.String("kind", "", "Kind")
	description := fs.String("description", "", "Description")
	plasmidID := fs.String("plasmid-id", "", "Plasmid ID")
	insert := fs.String("insert", "", "Insert")
	backbone := fs.String("backbone", "", "Backbone")
	resistance := fs.String("resistance", "", "Resistance list (comma-separated)")
	status := fs.String("status", "", "Status")
	location := fs.String("location", "", "Location")
	primers := fs.String("primers", "", "Primers")
	concentration := fs.Float64("concentration", 0, "Concentration (ng/uL)")
	sequenced := fs.String("sequenced", "", "Sequenced? (yes/no)")
	sequenceAA := fs.String("sequence-aa", "", "Sequence of insert/ORF (AA)")
	comments := fs.String("comments", "", "Comments")
	expressionPlasmidID := fs.Int("expression-plasmid-id", 0, "Plasmid registry ID")
	expressionStrain := fs.String("expression-strain", "", "Expression strain")
	virusID := fs.Int("virus-id", 0, "Virus registry ID")
	virusVolume := fs.Float64("virus-volume", 0, "Volume of virus used")
	startDate := fs.String("start-date", "", "Start date (YYYY-MM-DD)")
	harvestDate := fs.String("harvest-date", "", "Harvest date (YYYY-MM-DD)")
	volumePerFlask := fs.Float64("volume-per-flask", 0, "Volume per flask (L)")
	media := fs.String("media", "", "Media")
	totalVolume := fs.Float64("total-volume", 0, "Total volume (L)")
	iptgMm := fs.Float64("iptg-mm", 0, "[IPTG] induction (mM)")
	odInduction := fs.Float64("od-induction", 0, "OD induction")
	temperature := fs.Float64("temperature", 0, "Temperature")
	inductionTime := fs.String("induction-time", "", "Induction time")
	aliquot := fs.String("aliquot", "", "Aliquot")
	yfpHarvest := fs.String("yfp-harvest", "", "YFP at harvest")
	purified := fs.String("purified", "", "Purified? (yes/no)")
	expressionComment := fs.String("comment", "", "Comment")
	primerID := fs.String("primer-id", "", "Primer ID")
	primerType := fs.String("primer-type", "", "Primer type")
	primerSequence := fs.String("primer-sequence", "", "Primer sequence")
	primerLength := fs.Float64("primer-length", 0, "Primer length")
	primerMw := fs.Float64("primer-mw", 0, "Primer MW")
	primerGc := fs.Float64("primer-gc", 0, "Primer GC content")
	primerTm := fs.Float64("primer-tm", 0, "Primer Tm (C)")
	primerCompany := fs.String("primer-company", "", "Primer company")
	primerPurification := fs.String("primer-purification", "", "Primer purification")
	primerScale := fs.Float64("primer-scale", 0, "Primer scale (umol)")
	primerYieldUg := fs.Float64("primer-yield-ug", 0, "Primer yield (ug)")
	primerYieldNmol := fs.Float64("primer-yield-nmol", 0, "Primer yield (nmol)")
	primerConcUm := fs.Float64("primer-conc-um", 0, "Primer concentration (uM)")
	primerConcNgUl := fs.Float64("primer-conc-ngul", 0, "Primer concentration (ng/uL)")
	primerComment := fs.String("primer-comment", "", "Primer comment")
	gridID := fs.String("grid-id", "", "Grid ID")
	gridProject := fs.String("grid-project", "", "Grid project")
	gridType := fs.String("grid-type", "", "Grid type")
	gridMaterial := fs.String("grid-material", "", "Grid material")
	gridMesh := fs.String("grid-mesh", "", "Grid mesh size")
	gridHole := fs.String("grid-hole", "", "Grid hole size")
	gridThickness := fs.String("grid-thickness", "", "Grid thickness")
	gridLot := fs.String("grid-lot", "", "Grid lot number")
	gridStorage := fs.String("grid-storage", "", "Grid storage location")
	gridStatus := fs.String("grid-status", "", "Grid status")
	sampleRefID := fs.Int("sample-ref-id", 0, "Sample (protein prep) registry ID")
	sampleConcentration := fs.String("sample-concentration", "", "Sample concentration")
	sampleBuffer := fs.String("sample-buffer", "", "Sample buffer")
	sampleAdditives := fs.String("sample-additives", "", "Sample additives")
	appliedVolume := fs.Float64("applied-volume-ul", 0, "Applied volume (uL)")
	blotTime := fs.Float64("blot-time-s", 0, "Blot time (s)")
	blotForce := fs.String("blot-force", "", "Blot force")
	humidity := fs.Float64("humidity", 0, "Humidity (%)")
	temperatureC := fs.Float64("temperature-c", 0, "Temperature (C)")
	plungeMedium := fs.String("plunge-medium", "", "Plunge medium")
	glowDischarge := fs.String("glow-discharge", "", "Glow discharge")
	iceQuality := fs.String("ice-quality", "", "Ice quality")
	microscope := fs.String("microscope", "", "Microscope")
	sessionID := fs.String("session-id", "", "Session ID")
	magnification := fs.Float64("magnification", 0, "Magnification")
	pixelSize := fs.Float64("pixel-size-a", 0, "Pixel size (A)")
	defocusRange := fs.String("defocus-range", "", "Defocus range")
	dose := fs.Float64("dose", 0, "Dose (e-/A^2)")
	moviesCollected := fs.Int("movies-collected", 0, "Movies collected")
	screeningNotes := fs.String("screening-notes", "", "Screening notes")
	bestAreas := fs.String("best-areas", "", "Best areas")
	issues := fs.String("issues", "", "Issues")
	linkedDatasets := fs.String("linked-datasets", "", "Linked datasets")
	linkedReports := fs.String("linked-reports", "", "Linked reports")
	aliquotLabel := fs.String("aliquot-label", "", "Aliquot label")
	concentrationMgMl := fs.Float64("concentration-mg-ml", 0, "Concentration (mg/mL)")
	concentrationUm := fs.Float64("concentration-um", 0, "Concentration (uM)")
	a260a280 := fs.Float64("a260-a280", 0, "A260/A280")
	molecularWeightDa := fs.Float64("molecular-weight-da", 0, "Molecular weight (Da)")
	molarExtinctionCoeff := fs.Float64("molar-extinction-coeff", 0, "Molar extinction coeff (M-1 cm-1)")
	storageBuffer := fs.String("storage-buffer", "", "Storage buffer")
	aliquotSize := fs.Float64("aliquot-size-ul", 0, "Aliquot size (uL)")
	plasmidRefID := fs.Int("plasmid-ref-id", 0, "Linked plasmid registry ID")
	expressionSystem := fs.String("expression-system", "", "Expression system")
	species := fs.String("species", "", "Species")
	available := fs.String("available", "", "Available? (yes/no)")
	preppedBy := fs.String("prepped-by", "", "Prepped by")
	preppedOn := fs.String("prepped-on", "", "Prepped on (YYYY-MM-DD)")
	aliquotCount := fs.Int("aliquot-count", 0, "# Aliquots")
	_ = fs.Parse(args)

	if strings.TrimSpace(*nameValue) == "" || strings.TrimSpace(*kind) == "" {
		exitOnError(errors.New("name and kind are required"))
	}

	normalizedKind := normalizeKind(*kind)
	payload := registryCreatePayload{
		Name: *nameValue,
		Kind: *kind,
	}
	if normalizedKind == "plasmid" {
		payload.Kind = "Plasmid"
	}
	if normalizedKind == "protein preparation" {
		payload.Kind = "Protein preparation"
	}
	if normalizedKind == "expression" {
		payload.Kind = "Expression"
	}
	if normalizedKind == "primers" {
		payload.Kind = "Primers"
	}
	if normalizedKind == "cryo em grid" {
		payload.Kind = "Cryo-EM Grid"
	}
	if strings.TrimSpace(*description) != "" {
		payload.Description = description
	}

	if normalizedKind == "plasmid" {
		meta := map[string]interface{}{}
		if strings.TrimSpace(*plasmidID) != "" {
			meta["plasmidId"] = *plasmidID
		}
		if strings.TrimSpace(*insert) != "" {
			meta["insert"] = *insert
		}
		if strings.TrimSpace(*backbone) != "" {
			meta["backbone"] = *backbone
		}
		if strings.TrimSpace(*resistance) != "" {
			meta["resistance"] = strings.Join(splitTags(*resistance), ", ")
		}
		if strings.TrimSpace(*status) != "" {
			meta["status"] = *status
		}
		if strings.TrimSpace(*location) != "" {
			meta["location"] = *location
		}
		if strings.TrimSpace(*primers) != "" {
			meta["primers"] = *primers
		}
		if *concentration > 0 {
			meta["concentrationNgUl"] = *concentration
		}
		if strings.TrimSpace(*sequenced) != "" {
			parsed, err := parseBool(*sequenced)
			exitOnError(err)
			meta["sequenced"] = parsed
		}
		if strings.TrimSpace(*sequenceAA) != "" {
			meta["sequenceAA"] = *sequenceAA
		}
		if strings.TrimSpace(*comments) != "" {
			meta["comments"] = *comments
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	if normalizedKind == "protein preparation" {
		meta := map[string]interface{}{}
		if strings.TrimSpace(*aliquotLabel) != "" {
			meta["aliquotLabel"] = *aliquotLabel
		}
		if *concentrationMgMl > 0 {
			meta["concentrationMgMl"] = *concentrationMgMl
		}
		if *concentrationUm > 0 {
			meta["concentrationUm"] = *concentrationUm
		}
		if *a260a280 > 0 {
			meta["a260a280"] = *a260a280
		}
		if *molecularWeightDa > 0 {
			meta["molecularWeightDa"] = *molecularWeightDa
		}
		if *molarExtinctionCoeff > 0 {
			meta["molarExtinctionCoeff"] = *molarExtinctionCoeff
		}
		if strings.TrimSpace(*storageBuffer) != "" {
			meta["storageBuffer"] = *storageBuffer
		}
		if *aliquotSize > 0 {
			meta["aliquotSizeUl"] = *aliquotSize
		}
		if *plasmidRefID > 0 {
			meta["plasmidRefId"] = *plasmidRefID
		}
		if strings.TrimSpace(*expressionSystem) != "" {
			meta["expressionSystem"] = *expressionSystem
		}
		if strings.TrimSpace(*species) != "" {
			meta["species"] = *species
		}
		if strings.TrimSpace(*available) != "" {
			parsed, err := parseBool(*available)
			exitOnError(err)
			meta["available"] = parsed
		}
		if strings.TrimSpace(*preppedBy) != "" {
			meta["preppedBy"] = *preppedBy
		}
		if strings.TrimSpace(*preppedOn) != "" {
			meta["preppedOn"] = *preppedOn
		}
		if *aliquotCount > 0 {
			meta["aliquotCount"] = *aliquotCount
		}
		if strings.TrimSpace(*location) != "" {
			meta["location"] = *location
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	if normalizedKind == "expression" {
		meta := map[string]interface{}{}
		if *expressionPlasmidID > 0 {
			meta["expressionPlasmidRefId"] = *expressionPlasmidID
		}
		if strings.TrimSpace(*expressionStrain) != "" {
			meta["expressionStrain"] = *expressionStrain
		}
		if *virusID > 0 {
			meta["virusRefId"] = *virusID
		}
		if *virusVolume > 0 {
			meta["virusVolume"] = *virusVolume
		}
		if strings.TrimSpace(*startDate) != "" {
			meta["startDate"] = *startDate
		}
		if strings.TrimSpace(*harvestDate) != "" {
			meta["harvestDate"] = *harvestDate
		}
		if *volumePerFlask > 0 {
			meta["volumePerFlaskL"] = *volumePerFlask
		}
		if strings.TrimSpace(*media) != "" {
			meta["media"] = *media
		}
		if *totalVolume > 0 {
			meta["totalVolumeL"] = *totalVolume
		}
		if *iptgMm > 0 {
			meta["iptgMm"] = *iptgMm
		}
		if *odInduction > 0 {
			meta["odInduction"] = *odInduction
		}
		if *temperature > 0 {
			meta["temperature"] = *temperature
		}
		if strings.TrimSpace(*inductionTime) != "" {
			meta["inductionTime"] = *inductionTime
		}
		if strings.TrimSpace(*aliquot) != "" {
			meta["aliquot"] = *aliquot
		}
		if strings.TrimSpace(*yfpHarvest) != "" {
			meta["yfpAtHarvest"] = *yfpHarvest
		}
		if strings.TrimSpace(*purified) != "" {
			parsed, err := parseBool(*purified)
			exitOnError(err)
			meta["purified"] = parsed
		}
		if strings.TrimSpace(*expressionComment) != "" {
			meta["expressionComment"] = *expressionComment
		}
		if strings.TrimSpace(*location) != "" {
			meta["location"] = *location
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	if normalizedKind == "primers" {
		meta := map[string]interface{}{}
		if strings.TrimSpace(*primerID) != "" {
			meta["primerId"] = *primerID
		}
		if strings.TrimSpace(*primerType) != "" {
			meta["primerType"] = *primerType
		}
		if strings.TrimSpace(*primerSequence) != "" {
			meta["primerSequence"] = *primerSequence
		}
		if *primerLength > 0 {
			meta["primerLength"] = *primerLength
		}
		if *primerMw > 0 {
			meta["primerMw"] = *primerMw
		}
		if *primerGc > 0 {
			meta["primerGcContent"] = *primerGc
		}
		if *primerTm > 0 {
			meta["primerTm"] = *primerTm
		}
		if strings.TrimSpace(*primerCompany) != "" {
			meta["primerCompany"] = *primerCompany
		}
		if strings.TrimSpace(*primerPurification) != "" {
			meta["primerPurification"] = *primerPurification
		}
		if *primerScale > 0 {
			meta["primerScaleUmol"] = *primerScale
		}
		if *primerYieldUg > 0 {
			meta["primerYieldUg"] = *primerYieldUg
		}
		if *primerYieldNmol > 0 {
			meta["primerYieldNmol"] = *primerYieldNmol
		}
		if *primerConcUm > 0 {
			meta["primerConcentrationUm"] = *primerConcUm
		}
		if *primerConcNgUl > 0 {
			meta["primerConcentrationNgUl"] = *primerConcNgUl
		}
		if strings.TrimSpace(*primerComment) != "" {
			meta["primerComment"] = *primerComment
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	if normalizedKind == "cryo em grid" {
		meta := map[string]interface{}{}
		if strings.TrimSpace(*gridID) != "" {
			meta["gridId"] = *gridID
		}
		if strings.TrimSpace(*gridProject) != "" {
			meta["gridProject"] = *gridProject
		}
		if strings.TrimSpace(*gridType) != "" {
			meta["gridType"] = *gridType
		}
		if strings.TrimSpace(*gridMaterial) != "" {
			meta["gridMaterial"] = *gridMaterial
		}
		if strings.TrimSpace(*gridMesh) != "" {
			meta["gridMeshSize"] = *gridMesh
		}
		if strings.TrimSpace(*gridHole) != "" {
			meta["gridHoleSize"] = *gridHole
		}
		if strings.TrimSpace(*gridThickness) != "" {
			meta["gridThickness"] = *gridThickness
		}
		if strings.TrimSpace(*gridLot) != "" {
			meta["gridLotNumber"] = *gridLot
		}
		if strings.TrimSpace(*gridStorage) != "" {
			meta["gridStorageLocation"] = *gridStorage
		}
		if strings.TrimSpace(*gridStatus) != "" {
			meta["gridStatus"] = *gridStatus
		}
		if *sampleRefID > 0 {
			meta["sampleRefId"] = *sampleRefID
		}
		if strings.TrimSpace(*sampleConcentration) != "" {
			meta["sampleConcentration"] = *sampleConcentration
		}
		if strings.TrimSpace(*sampleBuffer) != "" {
			meta["sampleBuffer"] = *sampleBuffer
		}
		if strings.TrimSpace(*sampleAdditives) != "" {
			meta["sampleAdditives"] = *sampleAdditives
		}
		if *appliedVolume > 0 {
			meta["appliedVolumeUl"] = *appliedVolume
		}
		if *blotTime > 0 {
			meta["blotTimeS"] = *blotTime
		}
		if strings.TrimSpace(*blotForce) != "" {
			meta["blotForce"] = *blotForce
		}
		if *humidity > 0 {
			meta["humidityPercent"] = *humidity
		}
		if *temperatureC > 0 {
			meta["temperatureC"] = *temperatureC
		}
		if strings.TrimSpace(*plungeMedium) != "" {
			meta["plungeMedium"] = *plungeMedium
		}
		if strings.TrimSpace(*glowDischarge) != "" {
			meta["glowDischarge"] = *glowDischarge
		}
		if strings.TrimSpace(*iceQuality) != "" {
			meta["iceQuality"] = *iceQuality
		}
		if strings.TrimSpace(*microscope) != "" {
			meta["microscope"] = *microscope
		}
		if strings.TrimSpace(*sessionID) != "" {
			meta["sessionId"] = *sessionID
		}
		if *magnification > 0 {
			meta["magnification"] = *magnification
		}
		if *pixelSize > 0 {
			meta["pixelSizeA"] = *pixelSize
		}
		if strings.TrimSpace(*defocusRange) != "" {
			meta["defocusRange"] = *defocusRange
		}
		if *dose > 0 {
			meta["doseEPerA2"] = *dose
		}
		if *moviesCollected > 0 {
			meta["moviesCollected"] = *moviesCollected
		}
		if strings.TrimSpace(*screeningNotes) != "" {
			meta["screeningNotes"] = *screeningNotes
		}
		if strings.TrimSpace(*bestAreas) != "" {
			meta["bestAreas"] = *bestAreas
		}
		if strings.TrimSpace(*issues) != "" {
			meta["issues"] = *issues
		}
		if strings.TrimSpace(*linkedDatasets) != "" {
			meta["linkedDatasets"] = *linkedDatasets
		}
		if strings.TrimSpace(*linkedReports) != "" {
			meta["linkedReports"] = *linkedReports
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	return *id, payload
}

func parseRegistryPatchPayloadWithID(name string, args []string, existing *registryItem) (int, registryPatchPayload) {
	fs := flag.NewFlagSet(name, flag.ExitOnError)
	id := fs.Int("id", 0, "Registry ID")
	nameValue := fs.String("name", "", "Name")
	kind := fs.String("kind", "", "Kind")
	description := fs.String("description", "", "Description")
	plasmidID := fs.String("plasmid-id", "", "Plasmid ID")
	insert := fs.String("insert", "", "Insert")
	backbone := fs.String("backbone", "", "Backbone")
	resistance := fs.String("resistance", "", "Resistance list (comma-separated)")
	status := fs.String("status", "", "Status")
	location := fs.String("location", "", "Location")
	primers := fs.String("primers", "", "Primers")
	concentration := fs.Float64("concentration", 0, "Concentration (ng/uL)")
	sequenced := fs.String("sequenced", "", "Sequenced? (yes/no)")
	sequenceAA := fs.String("sequence-aa", "", "Sequence of insert/ORF (AA)")
	comments := fs.String("comments", "", "Comments")
	expressionPlasmidID := fs.Int("expression-plasmid-id", 0, "Plasmid registry ID")
	expressionStrain := fs.String("expression-strain", "", "Expression strain")
	virusID := fs.Int("virus-id", 0, "Virus registry ID")
	virusVolume := fs.Float64("virus-volume", 0, "Volume of virus used")
	startDate := fs.String("start-date", "", "Start date (YYYY-MM-DD)")
	harvestDate := fs.String("harvest-date", "", "Harvest date (YYYY-MM-DD)")
	volumePerFlask := fs.Float64("volume-per-flask", 0, "Volume per flask (L)")
	media := fs.String("media", "", "Media")
	totalVolume := fs.Float64("total-volume", 0, "Total volume (L)")
	iptgMm := fs.Float64("iptg-mm", 0, "[IPTG] induction (mM)")
	odInduction := fs.Float64("od-induction", 0, "OD induction")
	temperature := fs.Float64("temperature", 0, "Temperature")
	inductionTime := fs.String("induction-time", "", "Induction time")
	aliquot := fs.String("aliquot", "", "Aliquot")
	yfpHarvest := fs.String("yfp-harvest", "", "YFP at harvest")
	purified := fs.String("purified", "", "Purified? (yes/no)")
	expressionComment := fs.String("comment", "", "Comment")
	primerID := fs.String("primer-id", "", "Primer ID")
	primerType := fs.String("primer-type", "", "Primer type")
	primerSequence := fs.String("primer-sequence", "", "Primer sequence")
	primerLength := fs.Float64("primer-length", 0, "Primer length")
	primerMw := fs.Float64("primer-mw", 0, "Primer MW")
	primerGc := fs.Float64("primer-gc", 0, "Primer GC content")
	primerTm := fs.Float64("primer-tm", 0, "Primer Tm (C)")
	primerCompany := fs.String("primer-company", "", "Primer company")
	primerPurification := fs.String("primer-purification", "", "Primer purification")
	primerScale := fs.Float64("primer-scale", 0, "Primer scale (umol)")
	primerYieldUg := fs.Float64("primer-yield-ug", 0, "Primer yield (ug)")
	primerYieldNmol := fs.Float64("primer-yield-nmol", 0, "Primer yield (nmol)")
	primerConcUm := fs.Float64("primer-conc-um", 0, "Primer concentration (uM)")
	primerConcNgUl := fs.Float64("primer-conc-ngul", 0, "Primer concentration (ng/uL)")
	primerComment := fs.String("primer-comment", "", "Primer comment")
	gridID := fs.String("grid-id", "", "Grid ID")
	gridProject := fs.String("grid-project", "", "Grid project")
	gridType := fs.String("grid-type", "", "Grid type")
	gridMaterial := fs.String("grid-material", "", "Grid material")
	gridMesh := fs.String("grid-mesh", "", "Grid mesh size")
	gridHole := fs.String("grid-hole", "", "Grid hole size")
	gridThickness := fs.String("grid-thickness", "", "Grid thickness")
	gridLot := fs.String("grid-lot", "", "Grid lot number")
	gridStorage := fs.String("grid-storage", "", "Grid storage location")
	gridStatus := fs.String("grid-status", "", "Grid status")
	sampleRefID := fs.Int("sample-ref-id", 0, "Sample (protein prep) registry ID")
	sampleConcentration := fs.String("sample-concentration", "", "Sample concentration")
	sampleBuffer := fs.String("sample-buffer", "", "Sample buffer")
	sampleAdditives := fs.String("sample-additives", "", "Sample additives")
	appliedVolume := fs.Float64("applied-volume-ul", 0, "Applied volume (uL)")
	blotTime := fs.Float64("blot-time-s", 0, "Blot time (s)")
	blotForce := fs.String("blot-force", "", "Blot force")
	humidity := fs.Float64("humidity", 0, "Humidity (%)")
	temperatureC := fs.Float64("temperature-c", 0, "Temperature (C)")
	plungeMedium := fs.String("plunge-medium", "", "Plunge medium")
	glowDischarge := fs.String("glow-discharge", "", "Glow discharge")
	iceQuality := fs.String("ice-quality", "", "Ice quality")
	microscope := fs.String("microscope", "", "Microscope")
	sessionID := fs.String("session-id", "", "Session ID")
	magnification := fs.Float64("magnification", 0, "Magnification")
	pixelSize := fs.Float64("pixel-size-a", 0, "Pixel size (A)")
	defocusRange := fs.String("defocus-range", "", "Defocus range")
	dose := fs.Float64("dose", 0, "Dose (e-/A^2)")
	moviesCollected := fs.Int("movies-collected", 0, "Movies collected")
	screeningNotes := fs.String("screening-notes", "", "Screening notes")
	bestAreas := fs.String("best-areas", "", "Best areas")
	issues := fs.String("issues", "", "Issues")
	linkedDatasets := fs.String("linked-datasets", "", "Linked datasets")
	linkedReports := fs.String("linked-reports", "", "Linked reports")
	aliquotLabel := fs.String("aliquot-label", "", "Aliquot label")
	concentrationMgMl := fs.Float64("concentration-mg-ml", 0, "Concentration (mg/mL)")
	concentrationUm := fs.Float64("concentration-um", 0, "Concentration (uM)")
	a260a280 := fs.Float64("a260-a280", 0, "A260/A280")
	molecularWeightDa := fs.Float64("molecular-weight-da", 0, "Molecular weight (Da)")
	molarExtinctionCoeff := fs.Float64("molar-extinction-coeff", 0, "Molar extinction coeff (M-1 cm-1)")
	storageBuffer := fs.String("storage-buffer", "", "Storage buffer")
	aliquotSize := fs.Float64("aliquot-size-ul", 0, "Aliquot size (uL)")
	plasmidRefID := fs.Int("plasmid-ref-id", 0, "Linked plasmid registry ID")
	expressionSystem := fs.String("expression-system", "", "Expression system")
	species := fs.String("species", "", "Species")
	available := fs.String("available", "", "Available? (yes/no)")
	preppedBy := fs.String("prepped-by", "", "Prepped by")
	preppedOn := fs.String("prepped-on", "", "Prepped on (YYYY-MM-DD)")
	aliquotCount := fs.Int("aliquot-count", 0, "# Aliquots")
	_ = fs.Parse(args)

	if *id == 0 {
		exitOnError(errors.New("id is required"))
	}

	kindValue := strings.TrimSpace(*kind)
	if kindValue == "" && existing != nil {
		kindValue = existing.Kind
	}
	normalizedKind := normalizeKind(kindValue)

	payload := registryPatchPayload{}
	if strings.TrimSpace(*nameValue) != "" {
		value := strings.TrimSpace(*nameValue)
		payload.Name = &value
	}
	if strings.TrimSpace(*kind) != "" {
		normalized := strings.TrimSpace(*kind)
		switch normalizeKind(normalized) {
		case "plasmid":
			normalized = "Plasmid"
		case "protein preparation":
			normalized = "Protein preparation"
		case "expression":
			normalized = "Expression"
		case "primers":
			normalized = "Primers"
		case "cryo em grid":
			normalized = "Cryo-EM Grid"
		}
		payload.Kind = &normalized
	}
	if strings.TrimSpace(*description) != "" {
		payload.Description = description
	}

	if normalizedKind == "plasmid" {
		meta := map[string]interface{}{}
		if strings.TrimSpace(*plasmidID) != "" {
			meta["plasmidId"] = *plasmidID
		}
		if strings.TrimSpace(*insert) != "" {
			meta["insert"] = *insert
		}
		if strings.TrimSpace(*backbone) != "" {
			meta["backbone"] = *backbone
		}
		if strings.TrimSpace(*resistance) != "" {
			meta["resistance"] = strings.Join(splitTags(*resistance), ", ")
		}
		if strings.TrimSpace(*status) != "" {
			meta["status"] = *status
		}
		if strings.TrimSpace(*location) != "" {
			meta["location"] = *location
		}
		if strings.TrimSpace(*primers) != "" {
			meta["primers"] = *primers
		}
		if *concentration > 0 {
			meta["concentrationNgUl"] = *concentration
		}
		if strings.TrimSpace(*sequenced) != "" {
			parsed, err := parseBool(*sequenced)
			exitOnError(err)
			meta["sequenced"] = parsed
		}
		if strings.TrimSpace(*sequenceAA) != "" {
			meta["sequenceAA"] = *sequenceAA
		}
		if strings.TrimSpace(*comments) != "" {
			meta["comments"] = *comments
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	if normalizedKind == "protein preparation" {
		meta := map[string]interface{}{}
		if strings.TrimSpace(*aliquotLabel) != "" {
			meta["aliquotLabel"] = *aliquotLabel
		}
		if *concentrationMgMl > 0 {
			meta["concentrationMgMl"] = *concentrationMgMl
		}
		if *concentrationUm > 0 {
			meta["concentrationUm"] = *concentrationUm
		}
		if *a260a280 > 0 {
			meta["a260a280"] = *a260a280
		}
		if *molecularWeightDa > 0 {
			meta["molecularWeightDa"] = *molecularWeightDa
		}
		if *molarExtinctionCoeff > 0 {
			meta["molarExtinctionCoeff"] = *molarExtinctionCoeff
		}
		if strings.TrimSpace(*storageBuffer) != "" {
			meta["storageBuffer"] = *storageBuffer
		}
		if *aliquotSize > 0 {
			meta["aliquotSizeUl"] = *aliquotSize
		}
		if *plasmidRefID > 0 {
			meta["plasmidRefId"] = *plasmidRefID
		}
		if strings.TrimSpace(*expressionSystem) != "" {
			meta["expressionSystem"] = *expressionSystem
		}
		if strings.TrimSpace(*species) != "" {
			meta["species"] = *species
		}
		if strings.TrimSpace(*available) != "" {
			parsed, err := parseBool(*available)
			exitOnError(err)
			meta["available"] = parsed
		}
		if strings.TrimSpace(*preppedBy) != "" {
			meta["preppedBy"] = *preppedBy
		}
		if strings.TrimSpace(*preppedOn) != "" {
			meta["preppedOn"] = *preppedOn
		}
		if *aliquotCount > 0 {
			meta["aliquotCount"] = *aliquotCount
		}
		if strings.TrimSpace(*location) != "" {
			meta["location"] = *location
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	if normalizedKind == "expression" {
		meta := map[string]interface{}{}
		if *expressionPlasmidID > 0 {
			meta["expressionPlasmidRefId"] = *expressionPlasmidID
		}
		if strings.TrimSpace(*expressionStrain) != "" {
			meta["expressionStrain"] = *expressionStrain
		}
		if *virusID > 0 {
			meta["virusRefId"] = *virusID
		}
		if *virusVolume > 0 {
			meta["virusVolume"] = *virusVolume
		}
		if strings.TrimSpace(*startDate) != "" {
			meta["startDate"] = *startDate
		}
		if strings.TrimSpace(*harvestDate) != "" {
			meta["harvestDate"] = *harvestDate
		}
		if *volumePerFlask > 0 {
			meta["volumePerFlaskL"] = *volumePerFlask
		}
		if strings.TrimSpace(*media) != "" {
			meta["media"] = *media
		}
		if *totalVolume > 0 {
			meta["totalVolumeL"] = *totalVolume
		}
		if *iptgMm > 0 {
			meta["iptgMm"] = *iptgMm
		}
		if *odInduction > 0 {
			meta["odInduction"] = *odInduction
		}
		if *temperature > 0 {
			meta["temperature"] = *temperature
		}
		if strings.TrimSpace(*inductionTime) != "" {
			meta["inductionTime"] = *inductionTime
		}
		if strings.TrimSpace(*aliquot) != "" {
			meta["aliquot"] = *aliquot
		}
		if strings.TrimSpace(*yfpHarvest) != "" {
			meta["yfpAtHarvest"] = *yfpHarvest
		}
		if strings.TrimSpace(*purified) != "" {
			parsed, err := parseBool(*purified)
			exitOnError(err)
			meta["purified"] = parsed
		}
		if strings.TrimSpace(*expressionComment) != "" {
			meta["expressionComment"] = *expressionComment
		}
		if strings.TrimSpace(*location) != "" {
			meta["location"] = *location
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	if normalizedKind == "primers" {
		meta := map[string]interface{}{}
		if strings.TrimSpace(*primerID) != "" {
			meta["primerId"] = *primerID
		}
		if strings.TrimSpace(*primerType) != "" {
			meta["primerType"] = *primerType
		}
		if strings.TrimSpace(*primerSequence) != "" {
			meta["primerSequence"] = *primerSequence
		}
		if *primerLength > 0 {
			meta["primerLength"] = *primerLength
		}
		if *primerMw > 0 {
			meta["primerMw"] = *primerMw
		}
		if *primerGc > 0 {
			meta["primerGcContent"] = *primerGc
		}
		if *primerTm > 0 {
			meta["primerTm"] = *primerTm
		}
		if strings.TrimSpace(*primerCompany) != "" {
			meta["primerCompany"] = *primerCompany
		}
		if strings.TrimSpace(*primerPurification) != "" {
			meta["primerPurification"] = *primerPurification
		}
		if *primerScale > 0 {
			meta["primerScaleUmol"] = *primerScale
		}
		if *primerYieldUg > 0 {
			meta["primerYieldUg"] = *primerYieldUg
		}
		if *primerYieldNmol > 0 {
			meta["primerYieldNmol"] = *primerYieldNmol
		}
		if *primerConcUm > 0 {
			meta["primerConcentrationUm"] = *primerConcUm
		}
		if *primerConcNgUl > 0 {
			meta["primerConcentrationNgUl"] = *primerConcNgUl
		}
		if strings.TrimSpace(*primerComment) != "" {
			meta["primerComment"] = *primerComment
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	if normalizedKind == "cryo em grid" {
		meta := map[string]interface{}{}
		if strings.TrimSpace(*gridID) != "" {
			meta["gridId"] = *gridID
		}
		if strings.TrimSpace(*gridProject) != "" {
			meta["gridProject"] = *gridProject
		}
		if strings.TrimSpace(*gridType) != "" {
			meta["gridType"] = *gridType
		}
		if strings.TrimSpace(*gridMaterial) != "" {
			meta["gridMaterial"] = *gridMaterial
		}
		if strings.TrimSpace(*gridMesh) != "" {
			meta["gridMeshSize"] = *gridMesh
		}
		if strings.TrimSpace(*gridHole) != "" {
			meta["gridHoleSize"] = *gridHole
		}
		if strings.TrimSpace(*gridThickness) != "" {
			meta["gridThickness"] = *gridThickness
		}
		if strings.TrimSpace(*gridLot) != "" {
			meta["gridLotNumber"] = *gridLot
		}
		if strings.TrimSpace(*gridStorage) != "" {
			meta["gridStorageLocation"] = *gridStorage
		}
		if strings.TrimSpace(*gridStatus) != "" {
			meta["gridStatus"] = *gridStatus
		}
		if *sampleRefID > 0 {
			meta["sampleRefId"] = *sampleRefID
		}
		if strings.TrimSpace(*sampleConcentration) != "" {
			meta["sampleConcentration"] = *sampleConcentration
		}
		if strings.TrimSpace(*sampleBuffer) != "" {
			meta["sampleBuffer"] = *sampleBuffer
		}
		if strings.TrimSpace(*sampleAdditives) != "" {
			meta["sampleAdditives"] = *sampleAdditives
		}
		if *appliedVolume > 0 {
			meta["appliedVolumeUl"] = *appliedVolume
		}
		if *blotTime > 0 {
			meta["blotTimeS"] = *blotTime
		}
		if strings.TrimSpace(*blotForce) != "" {
			meta["blotForce"] = *blotForce
		}
		if *humidity > 0 {
			meta["humidityPercent"] = *humidity
		}
		if *temperatureC > 0 {
			meta["temperatureC"] = *temperatureC
		}
		if strings.TrimSpace(*plungeMedium) != "" {
			meta["plungeMedium"] = *plungeMedium
		}
		if strings.TrimSpace(*glowDischarge) != "" {
			meta["glowDischarge"] = *glowDischarge
		}
		if strings.TrimSpace(*iceQuality) != "" {
			meta["iceQuality"] = *iceQuality
		}
		if strings.TrimSpace(*microscope) != "" {
			meta["microscope"] = *microscope
		}
		if strings.TrimSpace(*sessionID) != "" {
			meta["sessionId"] = *sessionID
		}
		if *magnification > 0 {
			meta["magnification"] = *magnification
		}
		if *pixelSize > 0 {
			meta["pixelSizeA"] = *pixelSize
		}
		if strings.TrimSpace(*defocusRange) != "" {
			meta["defocusRange"] = *defocusRange
		}
		if *dose > 0 {
			meta["doseEPerA2"] = *dose
		}
		if *moviesCollected > 0 {
			meta["moviesCollected"] = *moviesCollected
		}
		if strings.TrimSpace(*screeningNotes) != "" {
			meta["screeningNotes"] = *screeningNotes
		}
		if strings.TrimSpace(*bestAreas) != "" {
			meta["bestAreas"] = *bestAreas
		}
		if strings.TrimSpace(*issues) != "" {
			meta["issues"] = *issues
		}
		if strings.TrimSpace(*linkedDatasets) != "" {
			meta["linkedDatasets"] = *linkedDatasets
		}
		if strings.TrimSpace(*linkedReports) != "" {
			meta["linkedReports"] = *linkedReports
		}
		if len(meta) > 0 {
			payload.Metadata = meta
		}
	}

	return *id, payload
}

func splitTags(value string) []string {
	if strings.TrimSpace(value) == "" {
		return []string{}
	}
	parts := strings.Split(value, ",")
	tags := make([]string, 0, len(parts))
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			tags = append(tags, trimmed)
		}
	}
	return tags
}

func filterRegistryItems(items []registryItem, query, kind string) []registryItem {
	query = strings.ToLower(strings.TrimSpace(query))
	kind = strings.ToLower(strings.TrimSpace(kind))
	filtered := make([]registryItem, 0, len(items))
	for _, item := range items {
		if kind != "" && strings.ToLower(item.Kind) != kind {
			continue
		}
		if query == "" {
			filtered = append(filtered, item)
			continue
		}
		description := ""
		if item.Description != nil {
			description = *item.Description
		}
		if strings.Contains(strings.ToLower(item.Name), query) ||
			strings.Contains(strings.ToLower(item.Kind), query) ||
			strings.Contains(strings.ToLower(description), query) ||
			metadataMatches(item.Metadata, query) {
			filtered = append(filtered, item)
		}
	}
	return filtered
}

func parseBool(value string) (bool, error) {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "yes", "true", "1":
		return true, nil
	case "no", "false", "0":
		return false, nil
	default:
		return false, fmt.Errorf("invalid boolean value: %s", value)
	}
}

func (c client) request(method, path string, payload interface{}) ([]byte, error) {
	var body io.Reader
	if payload != nil {
		data, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		body = bytes.NewReader(data)
	}
	req, err := http.NewRequest(method, c.baseURL+path, body)
	if err != nil {
		return nil, err
	}
	if authHeader := c.authHeader(); authHeader != "" {
		req.Header.Set("Authorization", "Bearer "+authHeader)
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	data, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, err
	}
	if res.StatusCode >= 300 {
		return nil, fmt.Errorf("request failed: %s", strings.TrimSpace(string(data)))
	}
	return data, nil
}

func (c client) requestNoAuth(method, path string, payload interface{}) ([]byte, error) {
	var body io.Reader
	if payload != nil {
		data, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		body = bytes.NewReader(data)
	}
	req, err := http.NewRequest(method, c.baseURL+path, body)
	if err != nil {
		return nil, err
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	data, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, err
	}
	if res.StatusCode >= 300 {
		return nil, fmt.Errorf("request failed: %s", strings.TrimSpace(string(data)))
	}
	return data, nil
}

func (c client) requestUpload(path, filePath string) ([]byte, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("file", filepath.Base(filePath))
	if err != nil {
		return nil, err
	}
	if _, err := io.Copy(part, file); err != nil {
		return nil, err
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", c.baseURL+path, &body)
	if err != nil {
		return nil, err
	}
	if authHeader := c.authHeader(); authHeader != "" {
		req.Header.Set("Authorization", "Bearer "+authHeader)
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	data, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, err
	}
	if res.StatusCode >= 300 {
		return nil, fmt.Errorf("request failed: %s", strings.TrimSpace(string(data)))
	}
	return data, nil
}

func getEnvOrDefault(key, fallback string) string {
	value := os.Getenv(key)
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func normalizeBaseURL(value string) string {
	trimmed := strings.TrimSpace(value)
	return strings.TrimRight(trimmed, "/")
}

func (c client) authHeader() string {
	if strings.TrimSpace(c.token) != "" {
		return c.token
	}
	if strings.TrimSpace(c.apiKey) != "" {
		return c.apiKey
	}
	return ""
}

func ensureToken(c client) error {
	if strings.TrimSpace(c.token) == "" {
		return errors.New("JWT token required. Set LABBOOK_TOKEN or --token")
	}
	return nil
}

func exitOnError(err error) {
	if err == nil {
		return
	}
	fmt.Fprintln(os.Stderr, "Error:", err)
	os.Exit(1)
}

func parseTemplatePayload(name string, args []string) templatePayload {
	fs := flag.NewFlagSet(name, flag.ExitOnError)
	templateName := fs.String("name", "", "Template name")
	contentHTML := fs.String("content-html", "", "HTML content")
	contentFile := fs.String("content-file", "", "Path to HTML file")
	_ = fs.Parse(args)

	if strings.TrimSpace(*templateName) == "" {
		exitOnError(errors.New("name is required"))
	}
	content := strings.TrimSpace(*contentHTML)
	if content == "" && strings.TrimSpace(*contentFile) != "" {
		data, err := os.ReadFile(*contentFile)
		exitOnError(err)
		content = string(data)
	}
	if content == "" {
		exitOnError(errors.New("content-html or content-file is required"))
	}

	return templatePayload{
		Name:        *templateName,
		ContentHTML: content,
	}
}

func normalizeKind(value string) string {
	normalized := strings.ToLower(strings.TrimSpace(value))
	normalized = strings.ReplaceAll(normalized, "-", " ")
	normalized = strings.Join(strings.Fields(normalized), " ")
	return normalized
}

func metadataMatches(metadata map[string]interface{}, query string) bool {
	if metadata == nil || query == "" {
		return false
	}
	for _, value := range metadata {
		if strings.Contains(strings.ToLower(fmt.Sprint(value)), query) {
			return true
		}
	}
	return false
}

func writeOutput(path string, data []byte) error {
	if strings.TrimSpace(path) == "" {
		fmt.Println(string(data))
		return nil
	}
	return os.WriteFile(path, data, 0644)
}

func parseVars(vars string, varsFile string) map[string]interface{} {
	if strings.TrimSpace(vars) == "" && strings.TrimSpace(varsFile) == "" {
		return map[string]interface{}{}
	}
	if strings.TrimSpace(varsFile) != "" {
		data, err := os.ReadFile(varsFile)
		exitOnError(err)
		var payload map[string]interface{}
		exitOnError(json.Unmarshal(data, &payload))
		return payload
	}
	var payload map[string]interface{}
	exitOnError(json.Unmarshal([]byte(vars), &payload))
	return payload
}

func parseMetadataPayload(metadata string, metadataFile string) map[string]interface{} {
	if strings.TrimSpace(metadata) == "" && strings.TrimSpace(metadataFile) == "" {
		return nil
	}
	var payload map[string]interface{}
	if strings.TrimSpace(metadataFile) != "" {
		data, err := os.ReadFile(metadataFile)
		exitOnError(err)
		exitOnError(json.Unmarshal(data, &payload))
		return payload
	}
	exitOnError(json.Unmarshal([]byte(metadata), &payload))
	return payload
}

type stringList []string

func (s *stringList) String() string {
	return strings.Join(*s, ",")
}

func (s *stringList) Set(value string) error {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	*s = append(*s, value)
	return nil
}

func parseRegistryLinksPayload(raw string, filePath string) []entryRegistryLink {
	if strings.TrimSpace(raw) == "" && strings.TrimSpace(filePath) == "" {
		return nil
	}
	var payload []entryRegistryLink
	if strings.TrimSpace(filePath) != "" {
		data, err := os.ReadFile(filePath)
		exitOnError(err)
		exitOnError(json.Unmarshal(data, &payload))
		return payload
	}
	exitOnError(json.Unmarshal([]byte(raw), &payload))
	return payload
}

func parseWidgetsArrayPayload(raw string, filePath string) interface{} {
	if strings.TrimSpace(raw) == "" && strings.TrimSpace(filePath) == "" {
		return nil
	}
	var data []byte
	if strings.TrimSpace(filePath) != "" {
		b, err := os.ReadFile(filePath)
		exitOnError(err)
		data = b
	} else {
		data = []byte(raw)
	}
	var payload interface{}
	exitOnError(json.Unmarshal(data, &payload))
	if _, ok := payload.([]interface{}); !ok {
		exitOnError(errors.New("widgets must be a JSON array"))
	}
	return payload
}

func parseRegistryLinkSpec(spec string, linkType string) entryRegistryLink {
	spec = strings.TrimSpace(spec)
	if spec == "" {
		exitOnError(errors.New("empty registry link spec"))
	}
	parts := strings.SplitN(spec, ":", 2)
	idValue := strings.TrimSpace(parts[0])
	registryID, err := strconv.Atoi(idValue)
	exitOnError(err)
	link := entryRegistryLink{
		RegistryID: registryID,
		LinkType:   linkType,
	}
	if len(parts) > 1 {
		link.Details = parseKeyValueDetails(parts[1])
	}
	return link
}

func parseKeyValueDetails(raw string) map[string]interface{} {
	details := map[string]interface{}{}
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return details
	}
	fields := strings.Split(raw, ",")
	for _, field := range fields {
		kv := strings.SplitN(field, "=", 2)
		key := strings.TrimSpace(kv[0])
		if key == "" {
			continue
		}
		value := ""
		if len(kv) > 1 {
			value = strings.TrimSpace(kv[1])
		}
		details[key] = parseScalarValue(value)
	}
	return details
}

func parseScalarValue(value string) interface{} {
	if value == "" {
		return ""
	}
	if intValue, err := strconv.Atoi(value); err == nil {
		return intValue
	}
	if floatValue, err := strconv.ParseFloat(value, 64); err == nil {
		return floatValue
	}
	switch strings.ToLower(value) {
	case "true":
		return true
	case "false":
		return false
	}
	return value
}

func parseDetailsJSON(raw string) map[string]interface{} {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	var payload map[string]interface{}
	exitOnError(json.Unmarshal([]byte(raw), &payload))
	return payload
}

func fetchEntryByID(c client, id int) (entryItem, error) {
	body, err := c.request("GET", fmt.Sprintf("/api/entries/%d", id), nil)
	if err != nil {
		return entryItem{}, err
	}
	var entry entryItem
	if err := json.Unmarshal(body, &entry); err != nil {
		return entryItem{}, err
	}
	return entry, nil
}

func mergeMetadata(base, updates map[string]interface{}) map[string]interface{} {
	if base == nil && updates == nil {
		return nil
	}
	merged := map[string]interface{}{}
	for key, value := range base {
		merged[key] = value
	}
	for key, value := range updates {
		merged[key] = value
	}
	return merged
}

func fetchRegistryByID(c client, id int) (registryItem, error) {
	body, err := c.request("GET", fmt.Sprintf("/api/registry/%d", id), nil)
	if err != nil {
		return registryItem{}, err
	}
	var item registryItem
	if err := json.Unmarshal(body, &item); err != nil {
		return registryItem{}, err
	}
	return item, nil
}

func fetchAttachmentURL(c client, path string, attachmentID int) (string, string) {
	body, err := c.request("GET", path, nil)
	exitOnError(err)
	var attachments []attachment
	exitOnError(json.Unmarshal(body, &attachments))
	for _, file := range attachments {
		if file.ID == attachmentID {
			return file.FileUrl, file.FileName
		}
	}
	exitOnError(fmt.Errorf("attachment %d not found", attachmentID))
	return "", ""
}

func downloadFile(baseURL, fileURL, outPath string) error {
	if strings.TrimSpace(fileURL) == "" {
		return errors.New("file URL is empty")
	}
	target := fileURL
	if strings.HasPrefix(fileURL, "/") {
		target = strings.TrimRight(baseURL, "/") + fileURL
	}
	res, err := http.Get(target)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode >= 300 {
		return fmt.Errorf("download failed: %s", res.Status)
	}
	data, err := io.ReadAll(res.Body)
	if err != nil {
		return err
	}
	return os.WriteFile(outPath, data, 0644)
}
