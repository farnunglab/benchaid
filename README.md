# BenchAid

An AI agent for the wet lab. Built by the [Farnung Lab](https://farnunglab.com).

**[benchaid.farnunglab.com](https://benchaid.farnunglab.com)**

BenchAid accelerates your biochemistry and structural biology workflows -- from primer design to protein purification. It turns [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenAI Codex](https://openai.com/codex/), or any other agentic LLM into a knowledgeable lab partner that understands your proteins, buffers, cloning strategies, and experimental workflows.

## Quick Start

```bash
git clone https://github.com/farnunglab/benchaid.git
cd benchaid && codex #For OpenAI Codex
cd benchaid && clayde #For Anthropic's Claude Code
# Works with any of your favourite agents!
```

Now start any agentic LLM in this folder -- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [Codex](https://openai.com/codex/), or any other agent. On first launch the agent will walk you through filling in `USER.md`, `LAB.md`, and other config files for your lab.

```bash
cd benchaid && codex #For OpenAI Codex
cd benchaid && clayde #For Anthropic's Claude Code
# Works with any of your favourite agents!
```

Designing primers, calculating buffer recipes, verifying ORFs, optimizing codons, assembling multi-protein complexes, running PHENIX refinements, documenting experiments in your lab notebook is easy. Here are some examples:

```
> Design LIC primers for RPB1 from accession P24928
> What's the extinction coefficient of my His-TEV-DSIF construct?
> Calculate a 100 µL elongation complex assembly with 5.2 µM Pol II
```



## CLI Tools

### Python

| Tool | Script | Description |
|------|--------|-------------|
| Primer Designer | `scripts/primer_cli.py` | PCR primer design for LIC cloning, Gibson assembly, and sequencing |
| ProtParam | `scripts/protparam_cli.py` | Protein parameter calculation (MW, pI, extinction coefficient) |
| ORF Verifier | `scripts/orf_verifier_cli.py` | ORF verification via six-frame translation and UniProt comparison |
| Reactor | `scripts/reactor_cli.py` | Reaction buffer calculator with protein stock compensation |
| Plasmidsaurus | `scripts/plasmidsaurus_cli.py` | Fetch sequencing data from Plasmidsaurus API |
| Codon Optimize | `scripts/codon_optimize_cli.py` | Codon optimization via IDT API |
| Complex CLI | `scripts/complex_cli.py` | Complex formation recipe calculator |
| Notion CLI | `scripts/notion_cli.py` | Search and read Notion pages and databases |
| SnapGene | `scripts/snapgene_cli.py` | Parse SnapGene .dna files |

### Go

| Tool | Path | Description |
|------|------|-------------|
| LabBook CLI | `cmd/labbookCLI` | Electronic lab notebook entries, registry, templates, widgets |
| Codon Optimize | `cmd/codon_optimize` | Codon optimization via IDT API |
| Twist Order | `cmd/twist_order` | Order DNA synthesis from Twist Bioscience |
| Construct Boundary | `cmd/construct_boundary` | Predict optimal construct boundaries for expression |
| Construct Generator | `cmd/construct_generator` | Generate expression construct sequences |
| Quartzy | `cmd/quartzy` | Lab supply inventory and ordering |

## Skills

Skills give the AI specialized knowledge. Each skill has a `SKILL.md` with detailed instructions, making the agent an expert in that domain.

| Skill | Command | What it does |
|-------|---------|-------------|
| Primer Designer | `/primerdesigner` | Design LIC, Gibson, and sequencing primers |
| ProtParam | `/protparam` | Calculate protein biophysical parameters |
| ORF Verifier | `/orfverifier` | Verify ORFs in plasmids against UniProt |
| Reactor | `/reactor` | Calculate buffer recipes with stock compensation |
| LabBook | `/labbook` | Manage lab notebook entries and registry |
| Plasmidsaurus | `/plasmidsaurus` | Fetch and analyze sequencing results |
| Codon Optimize | `/codon-optimize` | Codon optimize sequences via IDT |
| Twist Order | `/twist-order` | Order gene synthesis from Twist |
| Complex Formation | `/complex-formation` | Calculate multi-protein complex recipes |
| Cloning | `/cloning` | Cloning strategy and vector selection |
| Insect Cell | `/insect-cell` | Baculovirus expression protocols |
| Construct Boundary | `/constructboundary` | Predict expression construct boundaries |
| Construct Generator | `/construct-generator` | Generate construct sequences |
| Gel Annotation | `/gel-annotation` | Annotate SDS-PAGE gel images |
| Notion | `/notion` | Search and read Notion databases |
| Quartzy | `/quartzy` | Lab supply inventory management |
| Zebra Label | `/zebra-label` | Print labels on Zebra ZD411 printer |
| SnapGene | `/snapgene` | Parse SnapGene .dna files |
| Phenix | `/phenix` | Cryo-EM refinement with Phenix |
| Servalcat | `/servalcat` | Cryo-EM refinement with Servalcat |

## Agent Configuration

BenchAid uses a layered configuration system that gives the agent persistent context about your lab:

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Entry point -- tells the agent to read AGENTS.md |
| `AGENTS.md` | Core instructions: memory system, safety rules, lab information sources |
| `USER.md` | Your profile: name, role, communication preferences |
| `LAB.md` | Your lab: research focus, members, approaches |
| `IDENTITY.md` | Agent personality and name |
| `SOUL.md` | Agent boundaries and behavior guidelines |
| `HEARTBEAT.md` | Periodic check-in checklist |
| `STOCKS.md` | Common lab buffers and stock solutions |
| `TOOLS.md` | Quick-reference notes for external tools |

### Memory System

BenchAid maintains continuity across sessions through:
- `memory/longterm_memory.md` -- durable facts, preferences, and lessons learned
- `memory/YYYY-MM-DD.md` -- daily session notes
- LabBook registry -- persistent database of plasmids, proteins, expressions, grids

## Project Structure

```
benchaid/
  CLAUDE.md               # Entry point
  AGENTS.md               # Agent instructions
  USER.md                 # User profile (customize)
  LAB.md                  # Lab description (customize)
  STOCKS.md               # Buffer/reagent definitions
  .env.example            # Environment variable template
  go.mod                  # Go module
  scripts/                # Python CLI tools
  cmd/                    # Go CLI tools
    labbookCLI/           # Lab notebook CLI
    codon_optimize/       # IDT codon optimization
    twist_order/          # Twist gene ordering
    construct_boundary/   # Construct boundary prediction
    construct_generator/  # Construct sequence generation
    quartzy/              # Lab supply management
  skills/                 # Skill definitions
    primerdesigner/       # Primer design
    protparam/            # Protein parameters
    orfverifier/          # ORF verification
    reactor/              # Buffer calculations
    labbook/              # Lab notebook
    complex-formation/    # Complex assembly
    cloning/              # Cloning strategies
    insect-cell/          # Baculovirus expression
    ...
  vectors/                # Vector sequence files
  memory/                 # Session memory (gitignored)
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required for different features:
- **IDT** -- codon optimization (`IDT_CLIENT_ID`, `IDT_CLIENT_SECRET`, `IDT_USERNAME`, `IDT_PASSWORD`)
- **Twist** -- gene ordering (`TWIST_API_KEY`)
- **Notion** -- protocols and scheduling (`NOTION_TOKEN`)
- **Quartzy** -- lab supplies (`QUARTZY_KEY`, `QUARTZY_LAB_ID`)
- **LabBook** -- lab notebook (`LABBOOK_API_KEY`)
- **Plasmidsaurus** -- sequencing (`PLASMIDSAURUS_CLIENT_ID`, `PLASMIDSAURUS_CLIENT_SECRET`)

## Integrations

BenchAid connects to external services to extend the agent's capabilities:

- **NCBI Entrez** -- sequence retrieval and accession lookup
- **Plasmidsaurus** -- sequencing data and results
- **Notion** -- protocols, scheduling, and lab databases
- **IDT** -- codon optimization
- **Twist Bioscience** -- gene synthesis ordering
- **BioPython** -- sequence analysis and manipulation
- **Primer3** -- thermodynamic primer design

## Requirements

- Python 3.10+
- Go 1.21+
- Biopython (`pip install biopython`)
- primer3-py (`pip install primer3-py`)

Optional:
- Playwright (for HTML template rendering)
- snapgene_reader (for .dna file parsing)

## Contributing

BenchAid is built by researchers for researchers, and we'd love your help making it better. The easiest way to contribute is by adding a new skill -- a `SKILL.md` file in `skills/your-skill/` that teaches the agent something new. Whether it's a protocol you run every week, a calculation you do by hand, or an instrument you wish had a better interface -- if it belongs on the bench, it belongs in BenchAid.

Check out existing skills in `skills/` for examples, and open a pull request on [GitHub](https://github.com/farnunglab/benchaid).

## License

MIT
