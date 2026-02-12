#!/usr/bin/env python3
"""
IDT Codon Optimization CLI

Optimize DNA/protein sequences for expression in a target organism using IDT's API.

Usage:
    codon_optimize_cli.py --sequence MKTLLLTLVVV... --organism insect
    codon_optimize_cli.py --accession NP_001234 --organism ecoli
    codon_optimize_cli.py --accession NP_001234 --residues 1-300 --organism human

Environment:
    IDT_CLIENT_ID      - IDT API client ID
    IDT_CLIENT_SECRET  - IDT API client secret
"""

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

# Auto-load .env file from project root
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value

# IDT API endpoints
IDT_AUTH_URL = "https://www.idtdna.com/Identityserver/connect/token"
IDT_CODON_URL = "https://www.idtdna.com/restapi/v1/CodonOpt/Optimize"

# Organism mapping for codon optimization (must match IDT's organism names exactly)
ORGANISM_MAP = {
    # Insect cells
    "insect": "Spodoptera frugiperda",
    "sf9": "Spodoptera frugiperda",
    "sf21": "Spodoptera frugiperda",
    "hi5": "Trichoplusia ni",
    "trichoplusia": "Trichoplusia ni",

    # E. coli
    "ecoli": "Escherichia coli K12",
    "e.coli": "Escherichia coli K12",
    "bacteria": "Escherichia coli K12",

    # Mammalian
    "human": "Homo sapiens (human)",
    "mammalian": "Homo sapiens (human)",
    "hek": "Homo sapiens (human)",
    "cho": "Cricetulus griseus (hamster)",

    # Yeast
    "yeast": "Saccharomyces cerevisiae",
    "pichia": "Pichia pastoris",
}

# Vector to organism inference
VECTOR_ORGANISM = {
    "438": "insect",
    "1-": "ecoli",
    "pvex": "human",
}


def get_idt_token(client_id: str, client_secret: str, username: str, password: str) -> str:
    """Get OAuth token from IDT using password grant."""
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "scope": "test",
        "username": username,
        "password": password
    }).encode()

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    req = urllib.request.Request(
        IDT_AUTH_URL,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            return result.get("access_token")
    except urllib.error.HTTPError as e:
        print(f"IDT auth error: {e.code} - {e.read().decode()}", file=sys.stderr)
        return None


def fetch_protein_sequence(accession: str) -> dict:
    """Fetch protein sequence from NCBI."""

    # Try NCBI protein database
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=protein&id={urllib.parse.quote(accession)}&rettype=fasta&retmode=text"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BenchAid/1.0"})
        with urllib.request.urlopen(req) as resp:
            fasta = resp.read().decode()
            lines = fasta.strip().split("\n")
            header = lines[0]
            sequence = "".join(lines[1:])

            # Extract gene name from header
            gene_name = accession
            if "[" in header:
                # Try to get gene name
                parts = header.split()
                for p in parts:
                    if not p.startswith(">") and not p.startswith("["):
                        gene_name = p
                        break

            return {
                "accession": accession,
                "name": gene_name,
                "sequence": sequence,
                "length": len(sequence),
                "type": "protein"
            }
    except urllib.error.HTTPError as e:
        print(f"NCBI fetch error: {e.code}", file=sys.stderr)
        return None


def extract_residues(sequence: str, residue_range: str) -> str:
    """Extract a residue range from sequence (1-indexed)."""
    if not residue_range:
        return sequence

    parts = residue_range.replace(" ", "").split("-")
    if len(parts) != 2:
        print(f"Invalid residue range: {residue_range}", file=sys.stderr)
        return sequence

    try:
        start = int(parts[0]) - 1  # Convert to 0-indexed
        end = int(parts[1])
        return sequence[start:end]
    except ValueError:
        print(f"Invalid residue range: {residue_range}", file=sys.stderr)
        return sequence


def infer_sequence_type(sequence: str) -> str:
    """Infer IDT sequence type for codon optimization."""
    seq = sequence.upper()
    for ch in seq:
        if ch in {"A", "C", "G", "T", "U", "N"}:
            continue
        return "aminoAcid"
    return "dna"


def optimize_codon_idt(sequence: str, organism: str, token: str, name: str = "Query", product_type: str = "gene") -> dict:
    """Call IDT codon optimization API.

    Args:
        sequence: Amino acid sequence
        organism: Target organism (will be mapped to IDT organism name)
        token: OAuth bearer token
        name: Name for the sequence
        product_type: 'gene' or 'gblock'
    """
    organism_name = ORGANISM_MAP.get(organism.lower(), organism)

    payload = json.dumps({
        "organism": organism_name,
        "sequenceType": infer_sequence_type(sequence),
        "productType": product_type,
        "optimizationItems": [
            {
                "Name": name,
                "Sequence": sequence
            }
        ]
    }).encode()

    req = urllib.request.Request(
        IDT_CODON_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            results = json.loads(resp.read().decode())
            # Results is a list, extract OptResult from first item
            if results and len(results) > 0:
                item = results[0]
                opt_result = item.get("OptResult", {})
                return {
                    "Name": item.get("Name"),
                    "FullSequence": opt_result.get("FullSequence", ""),
                    "ComplexityScore": opt_result.get("ComplexityScore"),
                    "ComplexitySummary": opt_result.get("ComplexitySummary"),
                    "RestrictionSites": opt_result.get("RestrictionSites"),
                    "Complexities": opt_result.get("Complexities", [])
                }
            return None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"IDT API error: {e.code} - {error_body}", file=sys.stderr)
        return None


def infer_organism_from_vector(vector: str) -> str:
    """Infer target organism from vector name."""
    vector_lower = vector.lower()
    for prefix, org in VECTOR_ORGANISM.items():
        if prefix in vector_lower:
            return org
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Codon optimize sequences using IDT API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --sequence MKTLLLTLVVVTL... --organism insect
  %(prog)s --accession NP_001234567 --organism ecoli
  %(prog)s --accession NP_001234567 --residues 1-300 --organism human
  %(prog)s --accession NP_001234567 --vector 438-C

Organisms:
  insect, sf9, sf21, hi5    → Spodoptera frugiperda / Trichoplusia ni
  ecoli, bacteria           → Escherichia coli
  human, mammalian, hek     → Homo sapiens
  cho                       → Cricetulus griseus

Vector inference:
  438-*   → insect
  1-*     → ecoli
  pVEX-*  → human
"""
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--sequence", "-s", help="Protein or DNA sequence")
    input_group.add_argument("--accession", "-a", help="NCBI protein accession (NP_, XP_, etc.)")

    parser.add_argument("--residues", "-r", help="Residue range to extract (e.g., 1-300)")
    parser.add_argument("--name", "-n", help="Gene/construct name")

    # Target organism
    org_group = parser.add_mutually_exclusive_group(required=True)
    org_group.add_argument("--organism", "-o", help="Target organism for optimization")
    org_group.add_argument("--vector", "-v", help="Target vector (infers organism)")

    # Output options
    parser.add_argument("--output", "-O", help="Output file (default: stdout)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--fasta", action="store_true", help="Output as FASTA")

    args = parser.parse_args()

    # Get credentials
    client_id = os.environ.get("IDT_CLIENT_ID")
    client_secret = os.environ.get("IDT_CLIENT_SECRET")
    username = os.environ.get("IDT_USERNAME")
    password = os.environ.get("IDT_PASSWORD")

    if not all([client_id, client_secret, username, password]):
        print("Error: IDT credentials must be set in .env:", file=sys.stderr)
        print("  IDT_CLIENT_ID", file=sys.stderr)
        print("  IDT_CLIENT_SECRET", file=sys.stderr)
        print("  IDT_USERNAME      (your IDT account email)", file=sys.stderr)
        print("  IDT_PASSWORD      (your IDT account password)", file=sys.stderr)
        sys.exit(1)

    # Get sequence
    if args.accession:
        print(f"Fetching {args.accession} from NCBI...", file=sys.stderr)
        seq_info = fetch_protein_sequence(args.accession)
        if not seq_info:
            print("Failed to fetch sequence", file=sys.stderr)
            sys.exit(1)
        sequence = seq_info["sequence"]
        name = args.name or seq_info["name"]
    else:
        sequence = args.sequence.upper().replace(" ", "").replace("\n", "")
        name = args.name or "Query"

    # Extract residue range if specified
    if args.residues:
        original_len = len(sequence)
        sequence = extract_residues(sequence, args.residues)
        print(f"Extracted residues {args.residues}: {original_len} → {len(sequence)} aa", file=sys.stderr)
        name = f"{name}_{args.residues.replace('-', '_')}"

    # Determine organism
    if args.vector:
        organism = infer_organism_from_vector(args.vector)
        if not organism:
            print(f"Could not infer organism from vector: {args.vector}", file=sys.stderr)
            sys.exit(1)
        print(f"Inferred organism from {args.vector}: {organism}", file=sys.stderr)
    else:
        organism = args.organism

    organism_name = ORGANISM_MAP.get(organism.lower(), organism)

    # Authenticate
    print(f"Authenticating with IDT...", file=sys.stderr)
    token = get_idt_token(client_id, client_secret, username, password)
    if not token:
        print("Failed to authenticate with IDT", file=sys.stderr)
        sys.exit(1)

    # Optimize
    print(f"Optimizing {len(sequence)} aa for {organism_name}...", file=sys.stderr)
    result = optimize_codon_idt(sequence, organism, token, name=name)

    if not result:
        print("Codon optimization failed", file=sys.stderr)
        sys.exit(1)

    # Format output
    optimized_dna = result.get("FullSequence", "")

    # Calculate GC content
    gc_count = optimized_dna.count("G") + optimized_dna.count("C")
    gc_content = (gc_count / len(optimized_dna) * 100) if optimized_dna else 0

    output_data = {
        "name": name,
        "organism": organism_name,
        "input_protein": sequence,
        "input_length_aa": len(sequence),
        "optimized_dna": optimized_dna,
        "optimized_length_bp": len(optimized_dna),
        "gc_content": gc_content,
        "complexity_score": result.get("ComplexityScore"),
        "complexity_summary": result.get("ComplexitySummary", ""),
        "restriction_sites": result.get("RestrictionSites", "")
    }

    # Output
    if args.json:
        output = json.dumps(output_data, indent=2)
    elif args.fasta:
        output = f">{name}_codon_optimized_{organism}\n{optimized_dna}"
    else:
        gc = output_data.get('gc_content')
        gc_str = f"{gc:.1f}%" if gc else "N/A"
        status = output_data.get('status', '')
        message = output_data.get('message', '')

        output = f"""
Codon Optimization Result
=========================
Name:           {name}
Organism:       {organism_name}
Input:          {len(sequence)} aa
Output:         {len(optimized_dna)} bp
GC Content:     {gc_str}
Status:         {status}
{f'Message:        {message}' if message else ''}

Optimized DNA Sequence:
{optimized_dna}
"""

    if args.output:
        Path(args.output).write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
