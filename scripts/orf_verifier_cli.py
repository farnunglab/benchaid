#!/usr/bin/env python3
"""
ORF Verifier CLI - Verify open reading frames in plasmid sequences.

Performs six-frame translation to find amino acid sequences in circular plasmids,
with support for automatic tag detection and detailed placement reports.
"""

import argparse
import json
import os
import re
import struct
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Tuple


# =============================================================================
# Tag Library
# =============================================================================

TAG_LIBRARY = [
    {"id": "his6", "name": "His6", "kind": "tag", "sequences": ["HHHHHH"],
     "description": "Polyhistidine tag for Ni-NTA purification."},
    {"id": "his10", "name": "His10", "kind": "tag", "sequences": ["HHHHHHHHHH"],
     "description": "Extended polyhistidine tag for stronger binding."},
    {"id": "nhis6_tev", "name": "N-His6-TEV", "kind": "tag",
     "sequences": ["MGSSHHHHHHENLYFQSNA"],
     "description": "N-terminal His6 tag followed by a TEV protease cleavage site."},
    {"id": "nhis6_mbp_n10_tev", "name": "N-His6-MBP-N10-TEV", "kind": "tag",
     "sequences": ["MGSSHHHHHHGSSMKIEEGKLVIWINGDKGYNGLAEVGKKFEKDTGIKVTVEHPDKLEEKFPQVAATGDGPDIIFWAHDRFGGYAQSGLLAEITPDKAFQDKLYPFTWDAVRYNGKLIAYPIAVEALSLIYNKDLLPNPPKTWEEIPALDKELKAKGKSALMFNLQEPYFTWPLIAADGGYAFKYENGKYDIKDVGVDNAGAKAGLTFLVDLIKNKHMNADTDYSIAEAAFNKGETAMTINGPWAWSNIDTSKVNYGVTVLPTFKGQPSKPFVGVLSAGINAASPNKELAKEFLENYLLTDEGLEAVNKDKPLGAVALKSYEEELAKDPRIAATMENAQKGEIMPNIPQMSAFWYAVRTAVINAASGRQTVDEALKDAQTNSSSNNNNNNNNNNLGIEENLYFQSNA"],
     "description": "Fusion of N-terminal His6, MBP solubility tag, N10 linker, and TEV protease cleavage site."},
    {"id": "strepII", "name": "StrepII", "kind": "tag", "sequences": ["WSHPQFEK"],
     "description": "Strep-Tactin affinity tag."},
    {"id": "flag", "name": "FLAG", "kind": "tag", "sequences": ["DYKDDDDK"],
     "description": "FLAG epitope tag."},
    {"id": "ha", "name": "HA", "kind": "tag", "sequences": ["YPYDVPDYA"],
     "description": "Hemagglutinin epitope tag."},
    {"id": "myc", "name": "Myc", "kind": "tag", "sequences": ["EQKLISEEDL"],
     "description": "c-Myc epitope tag."},
    {"id": "tev", "name": "TEV site", "kind": "tag", "sequences": ["ENLYFQG"],
     "description": "TEV protease cleavage site."},
    {"id": "hrv3c", "name": "HRV 3C site", "kind": "tag", "sequences": ["LEVLFQGP"],
     "description": "Human rhinovirus 3C protease site."},
    {"id": "sumo", "name": "SUMO", "kind": "tag",
     "sequences": ["MRGSHHHHHHGSMGGSMKQTLKETGGGSGGGGSGTLVSTGGSEEDK"],
     "description": "SUMO fusion to enhance solubility."},
    {"id": "ggggs", "name": "GGGGS", "kind": "linker", "sequences": ["GGGGS"],
     "description": "Flexible glycine-serine linker."},
    {"id": "ggggs2", "name": "(GGGGS)2", "kind": "linker", "sequences": ["GGGGSGGGGS"],
     "description": "Two repeats of the flexible linker."},
    {"id": "ggggs3", "name": "(GGGGS)3", "kind": "linker", "sequences": ["GGGGSGGGGSGGGGS"],
     "description": "Three repeats of the flexible linker."},
]


# =============================================================================
# Genetic Code
# =============================================================================

CODON_TABLE = {
    'TTT': 'F', 'TTC': 'F',
    'TTA': 'L', 'TTG': 'L', 'CTT': 'L', 'CTC': 'L', 'CTA': 'L', 'CTG': 'L',
    'ATT': 'I', 'ATC': 'I', 'ATA': 'I',
    'ATG': 'M',
    'GTT': 'V', 'GTC': 'V', 'GTA': 'V', 'GTG': 'V',
    'TCT': 'S', 'TCC': 'S', 'TCA': 'S', 'TCG': 'S', 'AGT': 'S', 'AGC': 'S',
    'CCT': 'P', 'CCC': 'P', 'CCA': 'P', 'CCG': 'P',
    'ACT': 'T', 'ACC': 'T', 'ACA': 'T', 'ACG': 'T',
    'GCT': 'A', 'GCC': 'A', 'GCA': 'A', 'GCG': 'A',
    'TAT': 'Y', 'TAC': 'Y',
    'TAA': '*', 'TAG': '*', 'TGA': '*',
    'CAT': 'H', 'CAC': 'H',
    'CAA': 'Q', 'CAG': 'Q',
    'AAT': 'N', 'AAC': 'N',
    'AAA': 'K', 'AAG': 'K',
    'GAT': 'D', 'GAC': 'D',
    'GAA': 'E', 'GAG': 'E',
    'TGT': 'C', 'TGC': 'C',
    'TGG': 'W',
    'CGT': 'R', 'CGC': 'R', 'CGA': 'R', 'CGG': 'R', 'AGA': 'R', 'AGG': 'R',
    'GGT': 'G', 'GGC': 'G', 'GGA': 'G', 'GGG': 'G',
}


def translate_codon(codon: str) -> Optional[str]:
    """Translate a single codon to amino acid."""
    codon = codon.upper()
    return CODON_TABLE.get(codon)


def get_allowed_start_codons(allow_alt: bool) -> set:
    """Get set of allowed start codons."""
    if allow_alt:
        return {"ATG", "GTG", "TTG"}
    return {"ATG"}


# =============================================================================
# Sequence Utilities
# =============================================================================

def sanitize_plasmid_sequence(seq: str) -> str:
    """Clean and validate plasmid DNA sequence."""
    sanitized = []
    for ch in seq:
        if ch.isspace():
            continue
        upper = ch.upper()
        if upper in 'ACGT':
            sanitized.append(upper)
        elif upper == 'N':
            raise ValueError("Ambiguous nucleotide 'N' not supported")
        elif upper not in '0123456789':  # Skip numbers (from GenBank format)
            if upper.isalpha():
                raise ValueError(f"Invalid nucleotide: {ch}")
    return ''.join(sanitized)


def sanitize_aa_sequence(seq: str) -> str:
    """Clean amino acid sequence."""
    return ''.join(ch.upper() for ch in seq if not ch.isspace())


def reverse_complement(seq: str) -> str:
    """Get reverse complement of DNA sequence."""
    complement = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}
    return ''.join(complement.get(base, 'N') for base in reversed(seq))


def translate_sequence(seq: str, frame: int) -> str:
    """Translate DNA sequence in given reading frame."""
    amino_acids = []
    idx = frame
    while idx + 3 <= len(seq):
        codon = seq[idx:idx + 3]
        aa = translate_codon(codon)
        amino_acids.append(aa if aa else 'X')
        idx += 3
    return ''.join(amino_acids)


def translate_linear(seq: str) -> Optional[str]:
    """Translate a linear DNA sequence."""
    if len(seq) % 3 != 0:
        return None
    amino_acids = []
    for i in range(0, len(seq), 3):
        codon = seq[i:i + 3]
        aa = translate_codon(codon)
        if aa is None:
            return None
        amino_acids.append(aa)
    return ''.join(amino_acids)


def extract_circular(seq: str, start: int, length: int) -> str:
    """Extract a subsequence from a circular sequence."""
    if length == 0:
        return ""
    seq_len = len(seq)
    if start + length <= seq_len:
        return seq[start:start + length]
    else:
        return seq[start:] + seq[:length - (seq_len - start)]


def build_codon_table(seq: str) -> list:
    """Build codon usage table from coding sequence."""
    if len(seq) % 3 != 0:
        return []
    table = []
    for i in range(0, len(seq), 3):
        codon = seq[i:i + 3]
        aa = translate_codon(codon)
        if aa:
            table.append([codon, aa])
    return table


# =============================================================================
# File Parsing
# =============================================================================

def parse_fasta(content: str) -> tuple:
    """Parse FASTA format, return (name, sequence)."""
    lines = content.strip().split('\n')
    name = ""
    sequence_lines = []

    for line in lines:
        line = line.strip()
        if line.startswith('>'):
            name = line[1:].split()[0]
        elif line:
            sequence_lines.append(line)

    return name, ''.join(sequence_lines)


def parse_genbank(content: str) -> tuple:
    """Parse GenBank format, return (name, sequence)."""
    name = ""
    sequence_lines = []
    in_origin = False

    for line in content.split('\n'):
        if line.startswith('LOCUS'):
            parts = line.split()
            if len(parts) > 1:
                name = parts[1]
        elif line.startswith('ORIGIN'):
            in_origin = True
        elif line.startswith('//'):
            in_origin = False
        elif in_origin:
            # Remove numbers and spaces from sequence lines
            seq = re.sub(r'[^ACGTacgt]', '', line)
            if seq:
                sequence_lines.append(seq)

    return name, ''.join(sequence_lines).upper()


def read_plasmid_file(filepath: str) -> tuple:
    """Read plasmid from file, auto-detect format."""
    with open(filepath, 'r') as f:
        content = f.read()

    if content.strip().startswith('>'):
        return parse_fasta(content)
    elif 'LOCUS' in content and 'ORIGIN' in content:
        return parse_genbank(content)
    else:
        # Try as raw sequence
        return ("Unknown", content.replace('\n', '').replace(' ', ''))


def fetch_ncbi_sequence(accession: str) -> tuple:
    """Fetch sequence from NCBI by accession number."""
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id={accession}&rettype=fasta&retmode=text"

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read().decode('utf-8')
            return parse_fasta(content)
    except urllib.error.URLError as e:
        raise ValueError(f"Failed to fetch NCBI accession {accession}: {e}")


def fetch_uniprot_sequence(query: str) -> tuple:
    """
    Fetch protein sequence from UniProt by entry name or accession.

    Args:
        query: UniProt entry name (e.g., 'INT3_HUMAN') or accession (e.g., 'Q68E01')

    Returns:
        Tuple of (accession, sequence)
    """
    # First try direct accession lookup
    url = f"https://rest.uniprot.org/uniprotkb/{query}.fasta"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read().decode('utf-8')
            if content.strip():
                lines = content.strip().split('\n')
                header = lines[0]
                sequence = ''.join(lines[1:])
                # Extract accession from header: >sp|Q68E01|INT3_HUMAN ...
                if '|' in header:
                    parts = header.split('|')
                    if len(parts) >= 2:
                        accession = parts[1]
                        return accession, sequence
                return query, sequence
    except urllib.error.HTTPError:
        pass

    # Try search by entry name (e.g., INT3_HUMAN)
    search_url = f"https://rest.uniprot.org/uniprotkb/search?query={query}+AND+organism_id:9606&format=fasta&size=1"
    try:
        with urllib.request.urlopen(search_url, timeout=30) as response:
            content = response.read().decode('utf-8')
            if content.strip():
                lines = content.strip().split('\n')
                header = lines[0]
                sequence = ''.join(lines[1:])
                if '|' in header:
                    parts = header.split('|')
                    if len(parts) >= 2:
                        return parts[1], sequence
                return query, sequence
    except urllib.error.URLError:
        pass

    raise ValueError(f"Could not fetch UniProt sequence for: {query}")


# =============================================================================
# Data Classes
# =============================================================================

class Strand(str, Enum):
    PLUS = "plus"
    MINUS = "minus"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    NOT_FOUND = "not-found"
    INDETERMINATE = "indeterminate"


@dataclass
class Placement:
    strand: str
    frame: int
    start_nt: int
    end_nt: int
    wraps_origin: bool
    length_nt: int


@dataclass
class ComponentReport:
    name: str
    kind: str
    aa_range: tuple
    nt_range: tuple
    sequence: str


@dataclass
class VariantReport:
    aa_sequence: str
    observed_aa_sequence: str
    coding_sequence: str
    codon_table: list
    components: list


@dataclass
class Discrepancy:
    level: str
    position: int
    expected: str
    observed: str


@dataclass
class VerificationReport:
    status: str
    placement: Optional[Placement] = None
    variant: Optional[VariantReport] = None
    amino_acid_identity: float = 0.0
    nucleotide_identity: float = 0.0
    discrepancies: list = field(default_factory=list)
    reason: Optional[str] = None


@dataclass
class CandidateMatch:
    strand: str
    frame: int
    start_nt: int
    end_nt: int
    wraps: bool
    length_nt: int
    amino_acid_identity: float
    discrepancies: list
    coding_sequence: str
    observed_aa_sequence: str
    detected_tags: list = field(default_factory=list)


# =============================================================================
# Clone Verification Data Classes
# =============================================================================

class CloneStatus(str, Enum):
    PERFECT = "perfect"
    SILENT_MUTATIONS = "silent"
    CONSERVATIVE = "conservative"
    MUTANT = "mutant"
    FRAMESHIFT = "frameshift"
    TRUNCATED = "truncated"
    FAILED = "failed"


@dataclass
class Feature:
    name: str
    type: str
    start: int
    end: int
    strand: str
    translation: Optional[str] = None


@dataclass
class Mismatch:
    position: int
    expected: str
    observed: str
    feature: Optional[str] = None
    codon_change: Optional[str] = None
    aa_change: Optional[str] = None


@dataclass
class Indel:
    position: int
    length: int
    sequence: str
    feature: Optional[str] = None
    causes_frameshift: bool = False


@dataclass
class AlignmentResult:
    aligned_expected: str
    aligned_sequencing: str
    score: int
    identity: float
    mismatches: List[Mismatch]
    insertions: List[Indel]
    deletions: List[Indel]
    matches: int
    covered_bases: int


@dataclass
class AAChange:
    position: int
    expected: str
    observed: str
    codon_expected: str
    codon_observed: str
    is_synonymous: bool


@dataclass
class ORFImpact:
    name: str
    expected_aa: str
    observed_aa: str
    aa_identity: float
    aa_changes: List[AAChange]
    has_frameshift: bool
    has_premature_stop: bool
    is_intact: bool


@dataclass
class CloneReport:
    status: str
    expected_name: str
    expected_length: int
    sequencing_name: str
    sequencing_length: int
    identity: float
    matches: int
    mismatches: List[Mismatch]
    insertions: List[Indel]
    deletions: List[Indel]
    orf_impacts: List[ORFImpact]
    coverage: float
    notes: List[str] = field(default_factory=list)

# =============================================================================
# Tag Detection
# =============================================================================

def get_auto_tag_candidates():
    """Build list of tag candidates for auto-detection."""
    candidates = []
    for tag in TAG_LIBRARY:
        for i, seq in enumerate(tag.get("sequences", [])):
            sanitized = sanitize_aa_sequence(seq)
            if sanitized:
                tag_id = tag["id"] if len(tag["sequences"]) == 1 else f"{tag['id']}-{i+1}"
                candidates.append({
                    "id": tag_id,
                    "name": tag["name"],
                    "kind": tag.get("kind", "tag"),
                    "sequence": sanitized,
                })
    return candidates


AUTO_TAG_CANDIDATES = get_auto_tag_candidates()


def find_prefix_tag(translation: str, position: int):
    """Find longest matching tag ending at position."""
    best = None
    best_length = 0
    for candidate in AUTO_TAG_CANDIDATES:
        seq = candidate["sequence"]
        length = len(seq)
        if length == 0 or position < length:
            continue
        if translation[position - length:position] == seq and length > best_length:
            best = candidate
            best_length = length
    return best


def find_suffix_tag(translation: str, position: int):
    """Find longest matching tag starting at position."""
    best = None
    best_length = 0
    for candidate in AUTO_TAG_CANDIDATES:
        seq = candidate["sequence"]
        length = len(seq)
        if length == 0 or position + length > len(translation):
            continue
        if translation[position:position + length] == seq and length > best_length:
            best = candidate
            best_length = length
    return best


# =============================================================================
# Core Verification
# =============================================================================

def compute_identity(expected: str, observed: str) -> tuple:
    """Compute sequence identity and list of discrepancies."""
    matches = 0
    discrepancies = []
    for idx, (exp, obs) in enumerate(zip(expected, observed)):
        if exp == obs:
            matches += 1
        else:
            discrepancies.append(Discrepancy(
                level="amino-acid",
                position=idx,
                expected=exp,
                observed=obs,
            ))
    identity = 1.0 if len(expected) == 0 else matches / len(expected)
    return identity, discrepancies


def has_internal_start_codon(coding_seq: str, allowed: set) -> bool:
    """Check if coding sequence has internal start codons."""
    if len(coding_seq) < 6:
        return False
    for i in range(3, len(coding_seq), 3):
        codon = coding_seq[i:i + 3]
        if codon in allowed:
            return True
    return False


def rev_index_to_plus(idx: int, seq_len: int) -> int:
    """Convert reverse strand index to plus strand position."""
    pos = idx % seq_len
    return seq_len - 1 - pos


def verify_orf(
    sequence: str,
    aa_sequence: str,
    name: str = "Query",
    allow_alt_start: bool = False,
    min_identity: float = 1.0,
    max_mismatches: int = 0,
    disallow_internal_met: bool = False,
) -> VerificationReport:
    """
    Verify that an amino acid sequence is present in a plasmid.

    Performs six-frame translation and searches for the target sequence.
    """
    # Sanitize inputs
    try:
        sequence = sanitize_plasmid_sequence(sequence)
    except ValueError as e:
        return VerificationReport(
            status=VerificationStatus.NOT_FOUND.value,
            reason=str(e),
        )

    aa_sequence = sanitize_aa_sequence(aa_sequence)

    if len(sequence) == 0:
        return VerificationReport(
            status=VerificationStatus.NOT_FOUND.value,
            reason="empty plasmid sequence",
        )

    if len(aa_sequence) == 0:
        return VerificationReport(
            status=VerificationStatus.NOT_FOUND.value,
            reason="empty amino acid sequence",
        )

    seq_len = len(sequence)
    seq_doubled = sequence + sequence
    rev = reverse_complement(sequence)
    rev_doubled = rev + rev

    allowed_starts = get_allowed_start_codons(allow_alt_start)

    # Translate all 6 frames
    plus_frames = {frame: translate_sequence(seq_doubled, frame) for frame in range(3)}
    minus_frames = {frame: translate_sequence(rev_doubled, frame) for frame in range(3)}

    matches = []
    visited = set()
    aa_len = len(aa_sequence)

    # Search plus strand
    for frame, translation in plus_frames.items():
        if len(translation) < aa_len:
            continue

        for aa_idx in range(len(translation) - aa_len + 1):
            observed = translation[aa_idx:aa_idx + aa_len]
            identity, discrepancies = compute_identity(aa_sequence, observed)

            if identity < min_identity:
                continue
            if len(discrepancies) > max_mismatches:
                continue

            start_nt_doubled = frame + aa_idx * 3
            if start_nt_doubled >= seq_len:
                continue

            length_nt = aa_len * 3
            if start_nt_doubled + length_nt > len(seq_doubled):
                continue

            wraps = start_nt_doubled + length_nt > seq_len
            start_nt = start_nt_doubled % seq_len
            end_nt = (start_nt + length_nt - 1) % seq_len

            coding_sequence = extract_circular(sequence, start_nt, length_nt)
            translated = translate_linear(coding_sequence)

            if translated is None or translated != observed:
                continue

            if disallow_internal_met and has_internal_start_codon(coding_sequence, allowed_starts):
                continue

            start_codon = coding_sequence[:3] if len(coding_sequence) >= 3 else None
            if start_codon not in allowed_starts:
                continue

            key = (Strand.PLUS.value, frame, start_nt, length_nt)
            if key in visited:
                continue
            visited.add(key)

            # Check for auto-detected tags
            detected_tags = []
            prefix_tag = find_prefix_tag(translation, aa_idx)
            suffix_tag = find_suffix_tag(translation, aa_idx + aa_len)
            if prefix_tag:
                detected_tags.append(("N-terminal", prefix_tag))
            if suffix_tag:
                detected_tags.append(("C-terminal", suffix_tag))

            matches.append(CandidateMatch(
                strand=Strand.PLUS.value,
                frame=frame,
                start_nt=start_nt,
                end_nt=end_nt,
                wraps=wraps,
                length_nt=length_nt,
                amino_acid_identity=identity,
                discrepancies=discrepancies,
                coding_sequence=coding_sequence,
                observed_aa_sequence=translated,
                detected_tags=detected_tags,
            ))

    # Search minus strand
    for frame, translation in minus_frames.items():
        if len(translation) < aa_len:
            continue

        for aa_idx in range(len(translation) - aa_len + 1):
            observed = translation[aa_idx:aa_idx + aa_len]
            identity, discrepancies = compute_identity(aa_sequence, observed)

            if identity < min_identity:
                continue
            if len(discrepancies) > max_mismatches:
                continue

            codon_start_rev = frame + aa_idx * 3
            if codon_start_rev >= seq_len:
                continue

            length_nt = aa_len * 3
            if codon_start_rev + length_nt > len(rev_doubled):
                continue

            wraps = codon_start_rev + length_nt > seq_len
            coding_sequence = rev_doubled[codon_start_rev:codon_start_rev + length_nt]
            translated = translate_linear(coding_sequence)

            if translated is None or translated != observed:
                continue

            if disallow_internal_met and has_internal_start_codon(coding_sequence, allowed_starts):
                continue

            start_codon = coding_sequence[:3] if len(coding_sequence) >= 3 else None
            if start_codon not in allowed_starts:
                continue

            start_nt = rev_index_to_plus(codon_start_rev, seq_len)
            end_nt = rev_index_to_plus(codon_start_rev + length_nt - 1, seq_len)

            key = (Strand.MINUS.value, frame, start_nt, length_nt)
            if key in visited:
                continue
            visited.add(key)

            # Check for auto-detected tags
            detected_tags = []
            prefix_tag = find_prefix_tag(translation, aa_idx)
            suffix_tag = find_suffix_tag(translation, aa_idx + aa_len)
            if prefix_tag:
                detected_tags.append(("N-terminal", prefix_tag))
            if suffix_tag:
                detected_tags.append(("C-terminal", suffix_tag))

            matches.append(CandidateMatch(
                strand=Strand.MINUS.value,
                frame=frame,
                start_nt=start_nt,
                end_nt=end_nt,
                wraps=wraps,
                length_nt=length_nt,
                amino_acid_identity=identity,
                discrepancies=discrepancies,
                coding_sequence=coding_sequence,
                observed_aa_sequence=translated,
                detected_tags=detected_tags,
            ))

    # Evaluate results
    if len(matches) == 0:
        return VerificationReport(
            status=VerificationStatus.NOT_FOUND.value,
            reason="no amino-acid matches found",
        )

    if len(matches) > 1:
        return VerificationReport(
            status=VerificationStatus.INDETERMINATE.value,
            reason=f"multiple placements detected ({len(matches)} matches)",
        )

    # Single match found
    match = matches[0]

    placement = Placement(
        strand=match.strand,
        frame=match.frame,
        start_nt=match.start_nt + 1,  # 1-indexed for output
        end_nt=match.end_nt + 1,
        wraps_origin=match.wraps,
        length_nt=match.length_nt,
    )

    components = [ComponentReport(
        name=f"{name} core",
        kind="core",
        aa_range=(0, len(aa_sequence)),
        nt_range=(0, len(aa_sequence) * 3),
        sequence=aa_sequence,
    )]

    # Add detected tags to components
    for position, tag in match.detected_tags:
        components.insert(0 if position == "N-terminal" else len(components), ComponentReport(
            name=f"Auto-detected {position}: {tag['name']}",
            kind=tag["kind"],
            aa_range=(0, len(tag["sequence"])),
            nt_range=(0, len(tag["sequence"]) * 3),
            sequence=tag["sequence"],
        ))

    variant = VariantReport(
        aa_sequence=aa_sequence,
        observed_aa_sequence=match.observed_aa_sequence,
        coding_sequence=match.coding_sequence,
        codon_table=build_codon_table(match.coding_sequence),
        components=[asdict(c) for c in components],
    )

    return VerificationReport(
        status=VerificationStatus.VERIFIED.value,
        placement=placement,
        variant=variant,
        amino_acid_identity=match.amino_acid_identity,
        nucleotide_identity=1.0,
        discrepancies=[asdict(d) for d in match.discrepancies],
    )


# =============================================================================
# Clone Verification
# =============================================================================

def sanitize_sequence(seq: str, allow_n: bool) -> str:
    """Clean and validate DNA sequence allowing optional ambiguous N."""
    sanitized = []
    for ch in seq:
        if ch.isspace():
            continue
        upper = ch.upper()
        if upper in 'ACGT':
            sanitized.append(upper)
        elif upper == 'N':
            if allow_n:
                sanitized.append(upper)
            else:
                raise ValueError("Ambiguous nucleotide 'N' not supported in expected sequence")
        elif upper not in '0123456789':
            if upper.isalpha():
                raise ValueError(f"Invalid nucleotide: {ch}")
    return ''.join(sanitized)


def parse_genbank_features(content: str) -> List[Feature]:
    """Extract features from GenBank format."""
    features = []
    in_features = False
    current_type = None
    current_loc = None
    qualifiers = {}
    translation_lines = []

    def flush_feature():
        nonlocal current_type, current_loc, qualifiers, translation_lines
        if not current_type or not current_loc:
            return
        name = qualifiers.get("gene") or qualifiers.get("label") or qualifiers.get("product") or current_type
        start, end, strand = parse_feature_location(current_loc)
        if start is None:
            current_type = None
            current_loc = None
            qualifiers = {}
            translation_lines = []
            return
        translation = None
        if translation_lines:
            translation = ''.join(translation_lines).replace('"', '').replace(' ', '')
        features.append(Feature(
            name=name,
            type=current_type,
            start=start,
            end=end,
            strand=strand,
            translation=translation,
        ))
        current_type = None
        current_loc = None
        qualifiers = {}
        translation_lines = []

    for line in content.split('\n'):
        if line.startswith('FEATURES'):
            in_features = True
            continue
        if not in_features:
            continue
        if line.startswith('ORIGIN') or line.startswith('//'):
            flush_feature()
            break
        match = re.match(r'^ {5}(\S+)\s+(.+)$', line)
        if match:
            flush_feature()
            current_type = match.group(1)
            current_loc = match.group(2).strip()
            continue
        qualifier_match = re.match(r'^ {21}/(\S+)=?(.*)$', line)
        if qualifier_match:
            key = qualifier_match.group(1)
            value = qualifier_match.group(2).strip()
            if key == "translation":
                translation_lines.append(value.strip('"'))
            else:
                qualifiers[key] = value.strip('"')
            continue
        if translation_lines and line.startswith(' ' * 21) and '"' not in line:
            translation_lines.append(line.strip().replace(' ', ''))
        elif translation_lines and '"' in line:
            translation_lines.append(line.strip().replace('"', '').replace(' ', ''))

    return features


def parse_feature_location(loc: str) -> Tuple[Optional[int], Optional[int], str]:
    strand = '+'
    loc = loc.replace(' ', '')
    if loc.startswith('complement(') and loc.endswith(')'):
        strand = '-'
        loc = loc[len('complement('):-1]
    if loc.startswith('join(') and loc.endswith(')'):
        loc = loc[len('join('):-1]
    loc = loc.replace('<', '').replace('>', '')
    numbers = re.findall(r'\d+', loc)
    if len(numbers) < 2:
        return None, None, strand
    start = int(numbers[0])
    end = int(numbers[-1])
    return start, end, strand


def read_expected_file(filepath: str) -> Tuple[str, str, List[Feature]]:
    """Read expected plasmid file (GenBank or FASTA)."""
    with open(filepath, 'r') as f:
        content = f.read()
    features = []
    if content.strip().startswith('>'):
        name, seq = parse_fasta(content)
    elif 'LOCUS' in content and 'ORIGIN' in content:
        name, seq = parse_genbank(content)
        features = parse_genbank_features(content)
    else:
        name = os.path.basename(filepath)
        seq = content
    seq = sanitize_sequence(seq, allow_n=False)
    return name or os.path.basename(filepath), seq, features


def read_sequencing_file(filepath: str) -> Tuple[str, str]:
    """Read sequencing results from FASTA/SEQ/AB1 formats."""
    ext = os.path.splitext(filepath)[1].lower()
    name = os.path.basename(filepath)
    if ext == ".ab1":
        seq = read_ab1_sequence(filepath)
    else:
        with open(filepath, 'r') as f:
            content = f.read()
        if content.strip().startswith('>'):
            name, seq = parse_fasta(content)
        else:
            seq = content
    seq = sanitize_sequence(seq, allow_n=True)
    return name or os.path.basename(filepath), seq


def read_ab1_sequence(filepath: str) -> str:
    """Extract called bases from ABI trace (.ab1)."""
    with open(filepath, 'rb') as f:
        data = f.read()
    if data[:4] != b'ABIF':
        raise ValueError("Invalid AB1 file header")

    dir_entry = parse_abif_dir_entry(data, 6)
    dir_offset = dir_entry.get("data_offset")
    dir_count = dir_entry.get("num_elements")
    if dir_offset is None or dir_count is None:
        raise ValueError("Invalid AB1 directory entry")

    entry_size = 28
    pbas_entry = None
    for i in range(dir_count):
        entry_offset = dir_offset + i * entry_size
        entry = parse_abif_dir_entry(data, entry_offset)
        if entry.get("tag") == b"PBAS" and entry.get("tag_number") == 1:
            pbas_entry = entry
            break
    if pbas_entry is None:
        raise ValueError("PBAS1 tag not found in AB1 file")

    seq_bytes = read_abif_data(data, pbas_entry)
    seq = seq_bytes.decode('ascii', errors='ignore')
    return seq


def parse_abif_dir_entry(data: bytes, offset: int) -> dict:
    """Parse an ABIF directory entry."""
    if offset + 28 > len(data):
        return {}
    tag = data[offset:offset + 4]
    tag_number = struct.unpack(">I", data[offset + 4:offset + 8])[0]
    elem_type = struct.unpack(">H", data[offset + 8:offset + 10])[0]
    elem_size = struct.unpack(">H", data[offset + 10:offset + 12])[0]
    num_elements = struct.unpack(">I", data[offset + 12:offset + 16])[0]
    data_size = struct.unpack(">I", data[offset + 16:offset + 20])[0]
    data_offset = struct.unpack(">I", data[offset + 20:offset + 24])[0]
    return {
        "tag": tag,
        "tag_number": tag_number,
        "elem_type": elem_type,
        "elem_size": elem_size,
        "num_elements": num_elements,
        "data_size": data_size,
        "data_offset": data_offset,
    }


def read_abif_data(data: bytes, entry: dict) -> bytes:
    """Read data for an ABIF entry."""
    size = entry.get("data_size", 0)
    offset = entry.get("data_offset", 0)
    if size <= 4:
        packed = struct.pack(">I", offset)
        return packed[-size:]
    if offset + size > len(data):
        raise ValueError("AB1 entry points outside file bounds")
    return data[offset:offset + size]


def trim_sequence(seq: str, ignore_ends: int) -> str:
    if ignore_ends <= 0:
        return seq
    if len(seq) <= ignore_ends * 2:
        return seq
    return seq[ignore_ends:-ignore_ends]


def rotate_sequence(seq: str, start: int) -> str:
    start = start % len(seq)
    return seq[start:] + seq[:start]


def shift_features(features: List[Feature], start: int, seq_len: int) -> List[Feature]:
    shifted = []
    for feat in features:
        new_start = ((feat.start - 1 - start) % seq_len) + 1
        new_end = ((feat.end - 1 - start) % seq_len) + 1
        shifted.append(Feature(
            name=feat.name,
            type=feat.type,
            start=new_start,
            end=new_end,
            strand=feat.strand,
            translation=feat.translation,
        ))
    return shifted


def feature_contains(feature: Feature, position: int, seq_len: int) -> bool:
    if feature.start <= feature.end:
        return feature.start <= position <= feature.end
    return position >= feature.start or position <= feature.end


def feature_for_position(features: List[Feature], position: int, seq_len: int) -> Optional[str]:
    for feat in features:
        if feature_contains(feat, position, seq_len):
            return feat.name
    return None


def feature_at_position(features: List[Feature], position: int, seq_len: int) -> Optional[Feature]:
    for feat in features:
        if feature_contains(feat, position, seq_len):
            return feat
    return None


def align_sequences(expected: str, observed: str, band_width: Optional[int] = None) -> AlignmentResult:
    """Global alignment with affine gap penalties."""
    match_score = 2
    mismatch_score = -1
    gap_open = -5
    gap_extend = -1

    n = len(expected)
    m = len(observed)
    neg_inf = -10**9

    tm = [bytearray(m + 1) for _ in range(n + 1)]
    tx = [bytearray(m + 1) for _ in range(n + 1)]
    ty = [bytearray(m + 1) for _ in range(n + 1)]

    prev_m = [neg_inf] * (m + 1)
    prev_x = [neg_inf] * (m + 1)
    prev_y = [neg_inf] * (m + 1)
    prev_m[0] = 0
    prev_x[0] = neg_inf
    prev_y[0] = neg_inf
    for j in range(1, m + 1):
        prev_x[j] = gap_open + gap_extend * j
        tx[0][j] = 1

    for i in range(1, n + 1):
        curr_m = [neg_inf] * (m + 1)
        curr_x = [neg_inf] * (m + 1)
        curr_y = [neg_inf] * (m + 1)
        curr_y[0] = gap_open + gap_extend * i
        ty[i][0] = 1

        j_start = 1
        j_end = m
        if band_width is not None:
            j_start = max(1, i - band_width)
            j_end = min(m, i + band_width)

        for j in range(j_start, j_end + 1):
            score = match_score if expected[i - 1] == observed[j - 1] else mismatch_score

            m_from_m = prev_m[j - 1]
            m_from_x = prev_x[j - 1]
            m_from_y = prev_y[j - 1]
            best_m = m_from_m
            tm_code = 0
            if m_from_x > best_m:
                best_m = m_from_x
                tm_code = 1
            if m_from_y > best_m:
                best_m = m_from_y
                tm_code = 2
            curr_m[j] = best_m + score
            tm[i][j] = tm_code

            x_from_m = curr_m[j - 1] + gap_open + gap_extend
            x_from_x = curr_x[j - 1] + gap_extend
            if x_from_m >= x_from_x:
                curr_x[j] = x_from_m
                tx[i][j] = 0
            else:
                curr_x[j] = x_from_x
                tx[i][j] = 1

            y_from_m = prev_m[j] + gap_open + gap_extend
            y_from_y = prev_y[j] + gap_extend
            if y_from_m >= y_from_y:
                curr_y[j] = y_from_m
                ty[i][j] = 0
            else:
                curr_y[j] = y_from_y
                ty[i][j] = 1

        prev_m, curr_m = curr_m, prev_m
        prev_x, curr_x = curr_x, prev_x
        prev_y, curr_y = curr_y, prev_y

    end_m = prev_m[m]
    end_x = prev_x[m]
    end_y = prev_y[m]
    state = "M"
    score = end_m
    if end_x > score:
        score = end_x
        state = "X"
    if end_y > score:
        score = end_y
        state = "Y"

    aligned_expected = []
    aligned_observed = []
    i = n
    j = m
    while i > 0 or j > 0:
        if state == "M":
            aligned_expected.append(expected[i - 1])
            aligned_observed.append(observed[j - 1])
            code = tm[i][j]
            i -= 1
            j -= 1
            if code == 0:
                state = "M"
            elif code == 1:
                state = "X"
            else:
                state = "Y"
        elif state == "X":
            aligned_expected.append("-")
            aligned_observed.append(observed[j - 1])
            code = tx[i][j]
            j -= 1
            state = "M" if code == 0 else "X"
        else:
            aligned_expected.append(expected[i - 1])
            aligned_observed.append("-")
            code = ty[i][j]
            i -= 1
            state = "M" if code == 0 else "Y"

    aligned_expected = ''.join(reversed(aligned_expected))
    aligned_observed = ''.join(reversed(aligned_observed))

    mismatches, insertions, deletions, matches, covered = summarize_alignment(aligned_expected, aligned_observed, expected)
    identity = 0.0 if len(expected) == 0 else matches / len(expected)

    return AlignmentResult(
        aligned_expected=aligned_expected,
        aligned_sequencing=aligned_observed,
        score=score,
        identity=identity,
        mismatches=mismatches,
        insertions=insertions,
        deletions=deletions,
        matches=matches,
        covered_bases=covered,
    )


def summarize_alignment(aligned_expected: str, aligned_observed: str, expected_seq: str) -> Tuple[List[Mismatch], List[Indel], List[Indel], int, int]:
    mismatches = []
    insertions = []
    deletions = []
    matches = 0
    covered = 0

    expected_pos = 0
    insert_seq = ""
    insert_pos = None
    del_seq = ""
    del_pos = None

    for e, o in zip(aligned_expected, aligned_observed):
        if e != "-":
            expected_pos += 1
        if e != "-" and o != "-":
            covered += 1
            if e == o:
                matches += 1
            else:
                mismatches.append(Mismatch(
                    position=expected_pos,
                    expected=e,
                    observed=o,
                ))
            if insert_seq:
                insertions.append(Indel(
                    position=insert_pos if insert_pos else expected_pos,
                    length=len(insert_seq),
                    sequence=insert_seq,
                ))
                insert_seq = ""
                insert_pos = None
            if del_seq:
                deletions.append(Indel(
                    position=del_pos if del_pos else expected_pos,
                    length=len(del_seq),
                    sequence=del_seq,
                ))
                del_seq = ""
                del_pos = None
        elif e == "-" and o != "-":
            if del_seq:
                deletions.append(Indel(
                    position=del_pos if del_pos else expected_pos,
                    length=len(del_seq),
                    sequence=del_seq,
                ))
                del_seq = ""
                del_pos = None
            if insert_seq == "":
                insert_pos = max(1, expected_pos)
            insert_seq += o
        elif e != "-" and o == "-":
            if insert_seq:
                insertions.append(Indel(
                    position=insert_pos if insert_pos else expected_pos,
                    length=len(insert_seq),
                    sequence=insert_seq,
                ))
                insert_seq = ""
                insert_pos = None
            if del_seq == "":
                del_pos = expected_pos
            del_seq += e

    if insert_seq:
        insertions.append(Indel(
            position=insert_pos if insert_pos else expected_pos,
            length=len(insert_seq),
            sequence=insert_seq,
        ))
    if del_seq:
        deletions.append(Indel(
            position=del_pos if del_pos else expected_pos,
            length=len(del_seq),
            sequence=del_seq,
        ))

    return mismatches, insertions, deletions, matches, covered


def build_expected_observed_map(aligned_expected: str, aligned_observed: str) -> dict:
    mapping = {}
    expected_pos = 0
    for e, o in zip(aligned_expected, aligned_observed):
        if e != "-":
            expected_pos += 1
            mapping[expected_pos] = o if o != "-" else None
    return mapping


def extract_feature_sequence(seq: str, feature: Feature) -> str:
    if feature.start <= feature.end:
        return seq[feature.start - 1:feature.end]
    return seq[feature.start - 1:] + seq[:feature.end]


def extract_observed_feature(aligned_expected: str, aligned_observed: str, feature: Feature, seq_len: int) -> str:
    observed = []
    expected_pos = 0
    for e, o in zip(aligned_expected, aligned_observed):
        if e != "-":
            expected_pos += 1
        in_feature = feature_contains(feature, expected_pos, seq_len)
        if e != "-" and in_feature and o != "-":
            observed.append(o)
        elif e == "-" and o != "-" and in_feature:
            observed.append(o)
    return ''.join(observed)


def compute_aa_identity(expected_aa: str, observed_aa: str) -> Tuple[float, List[AAChange]]:
    changes = []
    matches = 0
    length = min(len(expected_aa), len(observed_aa))
    for idx in range(length):
        exp = expected_aa[idx]
        obs = observed_aa[idx]
        if exp == obs:
            matches += 1
            continue
        changes.append(AAChange(
            position=idx + 1,
            expected=exp,
            observed=obs,
            codon_expected="",
            codon_observed="",
            is_synonymous=exp == obs,
        ))
    identity = 1.0 if len(expected_aa) == 0 else matches / len(expected_aa)
    return identity, changes


def annotate_aa_changes(changes: List[AAChange], expected_dna: str, observed_dna: str) -> List[AAChange]:
    for change in changes:
        idx = change.position - 1
        exp_codon = expected_dna[idx * 3:idx * 3 + 3]
        obs_codon = observed_dna[idx * 3:idx * 3 + 3]
        change.codon_expected = exp_codon
        change.codon_observed = obs_codon
        change.is_synonymous = change.expected == change.observed
    return changes


def has_premature_stop(aa_seq: str) -> bool:
    if not aa_seq:
        return False
    return '*' in aa_seq[:-1]


def is_conservative_change(expected: str, observed: str) -> bool:
    groups = [
        set("AVLIM"),
        set("FYW"),
        set("KRH"),
        set("DE"),
        set("STNQ"),
        set("GP"),
        set("C"),
    ]
    for group in groups:
        if expected in group and observed in group:
            return True
    return False


def reverse_complement_codon(codon: str) -> str:
    return reverse_complement(codon)


def annotate_mismatch_codons(mismatches: List[Mismatch], features: List[Feature], expected_seq: str, aligned_expected: str, aligned_observed: str) -> None:
    mapping = build_expected_observed_map(aligned_expected, aligned_observed)
    seq_len = len(expected_seq)
    for mismatch in mismatches:
        feat = feature_at_position(features, mismatch.position, seq_len)
        if not feat or feat.type.upper() != "CDS":
            continue
        if feat.strand == '+':
            if feat.start <= feat.end:
                pos_in_feature = mismatch.position - feat.start + 1
            else:
                if mismatch.position >= feat.start:
                    pos_in_feature = mismatch.position - feat.start + 1
                else:
                    pos_in_feature = (seq_len - feat.start + 1) + mismatch.position
            codon_index = (pos_in_feature - 1) // 3
            codon_start_pos = ((feat.start - 1 + codon_index * 3) % seq_len) + 1
            positions = [
                codon_start_pos,
                ((codon_start_pos) % seq_len) + 1,
                ((codon_start_pos + 1) % seq_len) + 1,
            ]
        else:
            if feat.start <= feat.end:
                pos_in_feature = feat.end - mismatch.position + 1
            else:
                if mismatch.position <= feat.end:
                    pos_in_feature = feat.end - mismatch.position + 1
                else:
                    pos_in_feature = (feat.end) + (seq_len - mismatch.position) + 1
            codon_index = (pos_in_feature - 1) // 3
            codon_start_pos = ((feat.end - 1 - codon_index * 3) % seq_len) + 1
            positions = [
                ((codon_start_pos - 2 - 1) % seq_len) + 1,
                ((codon_start_pos - 1 - 1) % seq_len) + 1,
                codon_start_pos,
            ]
        expected_codon = ''.join(expected_seq[p - 1] for p in positions)
        observed_bases = [mapping.get(p) for p in positions]
        if any(b is None for b in observed_bases):
            continue
        observed_codon = ''.join(observed_bases)
        if feat.strand == '-':
            expected_codon = reverse_complement_codon(expected_codon)
            observed_codon = reverse_complement_codon(observed_codon)
        mismatch.codon_change = f"{expected_codon}->{observed_codon}"
        expected_aa = translate_codon(expected_codon) or "X"
        observed_aa = translate_codon(observed_codon) or "X"
        if expected_aa != observed_aa:
            mismatch.aa_change = f"{expected_aa}->{observed_aa}"


def evaluate_clone_status(mismatches: List[Mismatch], insertions: List[Indel], deletions: List[Indel], orf_impacts: List[ORFImpact], max_mismatches: int, notes: List[str]) -> str:
    if len(mismatches) > max_mismatches:
        notes.append(f"Mismatch count {len(mismatches)} exceeds max {max_mismatches}")
        return CloneStatus.FAILED.value
    if any(o.has_frameshift for o in orf_impacts):
        return CloneStatus.FRAMESHIFT.value
    if any(o.has_premature_stop for o in orf_impacts):
        return CloneStatus.TRUNCATED.value
    if orf_impacts:
        aa_changes = [change for impact in orf_impacts for change in impact.aa_changes]
        if aa_changes:
            if all(is_conservative_change(c.expected, c.observed) for c in aa_changes):
                return CloneStatus.CONSERVATIVE.value
            return CloneStatus.MUTANT.value
    if mismatches or insertions or deletions:
        return CloneStatus.SILENT_MUTATIONS.value
    return CloneStatus.PERFECT.value


def verify_clone(expected_name: str, expected_seq: str, sequencing_name: str, sequencing_seq: str, features: List[Feature], max_mismatches: int, ignore_ends: int) -> CloneReport:
    sequencing_seq = trim_sequence(sequencing_seq, ignore_ends)

    candidates = [0]
    for feat in features:
        candidates.append(feat.start - 1)
    uniq_candidates = []
    for start in candidates:
        if start not in uniq_candidates:
            uniq_candidates.append(start)
    candidates = uniq_candidates[:10]

    best = None
    best_features = features
    best_seq = expected_seq
    best_orientation = "forward"
    band_width = 1000 if max(len(expected_seq), len(sequencing_seq)) > 50000 else None

    for start in candidates:
        rotated = rotate_sequence(expected_seq, start)
        shifted = shift_features(features, start, len(expected_seq))
        for orientation in ("forward", "reverse"):
            seq = sequencing_seq if orientation == "forward" else reverse_complement(sequencing_seq)
            result = align_sequences(rotated, seq, band_width=band_width)
            if best is None or result.identity > best.identity:
                best = result
                best_features = shifted
                best_seq = rotated
                best_orientation = orientation

    if best is None:
        return CloneReport(
            status=CloneStatus.FAILED.value,
            expected_name=expected_name,
            expected_length=len(expected_seq),
            sequencing_name=sequencing_name,
            sequencing_length=len(sequencing_seq),
            identity=0.0,
            matches=0,
            mismatches=[],
            insertions=[],
            deletions=[],
            orf_impacts=[],
            coverage=0.0,
            notes=["Alignment failed"],
        )

    for mismatch in best.mismatches:
        mismatch.feature = feature_for_position(best_features, mismatch.position, len(best_seq))
    for indel in best.insertions:
        feat = feature_at_position(best_features, indel.position, len(best_seq))
        indel.feature = feat.name if feat else None
        if feat and feat.type.upper() == "CDS" and indel.length % 3 != 0:
            indel.causes_frameshift = True
    for indel in best.deletions:
        feat = feature_at_position(best_features, indel.position, len(best_seq))
        indel.feature = feat.name if feat else None
        if feat and feat.type.upper() == "CDS" and indel.length % 3 != 0:
            indel.causes_frameshift = True
    annotate_mismatch_codons(best.mismatches, best_features, best_seq, best.aligned_expected, best.aligned_sequencing)

    orf_impacts = []
    for feat in best_features:
        if feat.type.upper() != "CDS":
            continue
        expected_dna = extract_feature_sequence(best_seq, feat)
        observed_dna = extract_observed_feature(best.aligned_expected, best.aligned_sequencing, feat, len(best_seq))
        if feat.strand == '-':
            expected_dna = reverse_complement(expected_dna)
            observed_dna = reverse_complement(observed_dna)
        expected_aa = feat.translation or translate_linear(expected_dna) or ""
        observed_aa = translate_linear(observed_dna)
        has_frameshift = observed_aa is None
        if observed_aa is None:
            observed_aa = ""
        aa_identity, changes = compute_aa_identity(expected_aa, observed_aa)
        changes = annotate_aa_changes(changes, expected_dna, observed_dna)
        impact = ORFImpact(
            name=feat.name,
            expected_aa=expected_aa,
            observed_aa=observed_aa,
            aa_identity=aa_identity,
            aa_changes=changes,
            has_frameshift=has_frameshift,
            has_premature_stop=has_premature_stop(observed_aa),
            is_intact=aa_identity == 1.0 and not has_frameshift and not has_premature_stop(observed_aa),
        )
        orf_impacts.append(impact)

    coverage = 0.0 if len(best_seq) == 0 else best.covered_bases / len(best_seq)
    notes = []
    if best_orientation == "reverse":
        notes.append("Sequencing read aligned as reverse complement")
    if coverage < 1.0:
        notes.append(f"Coverage {coverage * 100:.1f}% of expected plasmid")

    status = evaluate_clone_status(best.mismatches, best.insertions, best.deletions, orf_impacts, max_mismatches, notes)

    return CloneReport(
        status=status,
        expected_name=expected_name,
        expected_length=len(best_seq),
        sequencing_name=sequencing_name,
        sequencing_length=len(sequencing_seq),
        identity=best.identity,
        matches=best.matches,
        mismatches=best.mismatches,
        insertions=best.insertions,
        deletions=best.deletions,
        orf_impacts=orf_impacts,
        coverage=coverage,
        notes=notes,
    )

# =============================================================================
# Annotation Verification
# =============================================================================

@dataclass
class AnnotationResult:
    """Result of verifying a single CDS annotation against UniProt."""
    label: str
    uniprot_id: Optional[str]
    location: str
    plasmid_length: int
    uniprot_length: Optional[int]
    identity: float
    status: str  # PASS, FAIL, ERROR
    differences: List[dict] = field(default_factory=list)
    error: Optional[str] = None
    is_fragment: bool = False
    notes: Optional[str] = None


@dataclass
class AnnotationVerificationReport:
    """Full report for verifying all annotations in a plasmid."""
    plasmid_name: str
    plasmid_file: str
    total_cds: int
    passed: int
    failed: int
    errors: int
    results: List[AnnotationResult]


def extract_cds_annotations(filepath: str) -> List[dict]:
    """
    Extract CDS annotations from a GenBank file (e.g., pLannotate output).

    Returns list of dicts with: label, location, sequence, strand, identity, match_length, fragment
    """
    with open(filepath, 'r') as f:
        content = f.read()

    # Parse sequence
    _, sequence = parse_genbank(content)
    seq_len = len(sequence)

    annotations = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]

        # Look for CDS features
        if line.startswith('     CDS'):
            location_str = line[21:].strip()

            # Parse location
            strand = '+'
            if 'complement' in location_str:
                strand = '-'
                location_str = location_str.replace('complement(', '').rstrip(')')

            # Handle join() for split features
            location_str = location_str.replace('join(', '').rstrip(')')

            # Extract start and end
            numbers = re.findall(r'\d+', location_str)
            if len(numbers) >= 2:
                start = int(numbers[0])
                end = int(numbers[-1])
            else:
                i += 1
                continue

            # Collect qualifiers
            qualifiers = {}
            i += 1
            while i < len(lines) and lines[i].startswith(' ' * 21):
                qual_line = lines[i].strip()
                if qual_line.startswith('/'):
                    # Parse qualifier
                    if '=' in qual_line:
                        key, value = qual_line[1:].split('=', 1)
                        value = value.strip('"')
                        qualifiers[key] = value
                i += 1

            # Get label (pLannotate uses /label)
            label = qualifiers.get('label', qualifiers.get('gene', qualifiers.get('product', '')))

            if label:
                # Extract the DNA sequence for this CDS
                if start <= end:
                    dna_seq = sequence[start-1:end]
                else:
                    # Wraps around origin
                    dna_seq = sequence[start-1:] + sequence[:end]

                if strand == '-':
                    dna_seq = reverse_complement(dna_seq)

                # Translate
                protein_seq = translate_linear(dna_seq)
                if protein_seq and protein_seq.endswith('*'):
                    protein_seq = protein_seq[:-1]

                annotations.append({
                    'label': label,
                    'location': f"{start}..{end}",
                    'strand': strand,
                    'start': start,
                    'end': end,
                    'dna_sequence': dna_seq,
                    'protein_sequence': protein_seq,
                    'identity': qualifiers.get('identity', ''),
                    'match_length': qualifiers.get('match_length', ''),
                    'fragment': qualifiers.get('fragment', 'False').lower() == 'true',
                })
            continue

        i += 1

    return annotations


def verify_annotation(annotation: dict) -> AnnotationResult:
    """Verify a single CDS annotation against UniProt reference."""
    label = annotation['label']
    location = annotation['location']
    plasmid_protein = annotation.get('protein_sequence', '')
    is_fragment = annotation.get('fragment', False)

    # Clean up label for UniProt lookup - remove common suffixes
    lookup_label = label
    # Remove "(fragment)" and similar annotations
    lookup_label = re.sub(r'\s*\(fragment\)', '', lookup_label, flags=re.IGNORECASE)
    lookup_label = re.sub(r'\s*\(partial\)', '', lookup_label, flags=re.IGNORECASE)
    lookup_label = lookup_label.strip()

    if not plasmid_protein:
        return AnnotationResult(
            label=label,
            uniprot_id=None,
            location=location,
            plasmid_length=0,
            uniprot_length=None,
            identity=0.0,
            status="ERROR",
            error="Could not translate CDS",
            is_fragment=is_fragment,
        )

    # Try to fetch UniProt sequence
    try:
        uniprot_id, uniprot_seq = fetch_uniprot_sequence(lookup_label)
    except ValueError as e:
        return AnnotationResult(
            label=label,
            uniprot_id=None,
            location=location,
            plasmid_length=len(plasmid_protein),
            uniprot_length=None,
            identity=0.0,
            status="ERROR",
            error=str(e),
            is_fragment=is_fragment,
        )

    # Compare sequences
    plasmid_len = len(plasmid_protein)
    uniprot_len = len(uniprot_seq)

    # First check: is plasmid sequence identical to full UniProt?
    if plasmid_protein == uniprot_seq:
        return AnnotationResult(
            label=label,
            uniprot_id=uniprot_id,
            location=location,
            plasmid_length=plasmid_len,
            uniprot_length=uniprot_len,
            identity=1.0,
            status="PASS",
            differences=[],
            is_fragment=is_fragment,
        )

    # Second check: is plasmid a perfect substring of UniProt? (N/C-terminal truncation)
    if plasmid_protein in uniprot_seq:
        # Find where in UniProt it matches
        match_start = uniprot_seq.find(plasmid_protein)
        match_end = match_start + plasmid_len

        # Build truncation notes
        truncation_notes = []
        if match_start > 0:
            truncation_notes.append(f"N-term truncated: starts at UniProt position {match_start + 1}")
        if match_end < uniprot_len:
            truncation_notes.append(f"C-term truncated: ends at UniProt position {match_end}")

        # This is a valid truncation - 100% identity on matched region
        return AnnotationResult(
            label=label,
            uniprot_id=uniprot_id,
            location=location,
            plasmid_length=plasmid_len,
            uniprot_length=uniprot_len,
            identity=1.0,  # 100% on matched region
            status="PASS",  # Valid if perfect match on expressed region
            differences=[],
            is_fragment=is_fragment,
            notes="; ".join(truncation_notes) if truncation_notes else None,
        )

    # Third check: align from N-terminus and look for mutations
    matches = 0
    differences = []
    min_len = min(plasmid_len, uniprot_len)

    for i in range(min_len):
        if plasmid_protein[i] == uniprot_seq[i]:
            matches += 1
        else:
            differences.append({
                'position': i + 1,
                'expected': uniprot_seq[i],
                'observed': plasmid_protein[i],
            })

    # Identity based on UniProt length (reference)
    identity = matches / uniprot_len if uniprot_len > 0 else 0.0

    # Determine status - only 100% identity is PASS
    if identity == 1.0 and plasmid_len == uniprot_len:
        status = "PASS"
    else:
        status = "FAIL"

    return AnnotationResult(
        label=label,
        uniprot_id=uniprot_id,
        location=location,
        plasmid_length=plasmid_len,
        uniprot_length=uniprot_len,
        identity=identity,
        status=status,
        differences=differences[:10],  # Limit to first 10 differences
        is_fragment=is_fragment,
    )


def verify_annotations(filepath: str, targets_only: bool = False, organism: str = None) -> AnnotationVerificationReport:
    """
    Verify all CDS annotations in a GenBank file against UniProt.

    Args:
        filepath: Path to GenBank file with pLannotate annotations
        targets_only: If True, only verify target proteins (HUMAN, MOUSE, BOVIN), skip vector components
        organism: Filter to specific organism code (e.g., 'HUMAN')

    Returns:
        AnnotationVerificationReport with results for all CDS
    """
    # Target organisms for expression (skip E. coli vector components)
    TARGET_ORGANISMS = {'HUMAN', 'MOUSE', 'RAT', 'BOVIN', 'YEAST', 'DROME', 'XENLA', 'ARATH'}
    VECTOR_ORGANISMS = {'ECOLI', 'ECOLX', 'ECOL6', 'LACC1', 'BPT4', 'BPT7', 'PHAGE'}
    # Get plasmid name
    with open(filepath, 'r') as f:
        content = f.read()

    plasmid_name = "Unknown"
    for line in content.split('\n'):
        if line.startswith('LOCUS'):
            parts = line.split()
            if len(parts) > 1:
                plasmid_name = parts[1]
            break

    # Extract annotations
    annotations = extract_cds_annotations(filepath)

    # Filter to only protein-coding annotations (skip things like promoters, terminators)
    protein_annotations = [
        a for a in annotations
        if '_' in a['label'] and a['protein_sequence']  # e.g., INT3_HUMAN, MED29_HUMAN
    ]

    # Apply organism filtering
    if organism:
        # Filter to specific organism
        protein_annotations = [
            a for a in protein_annotations
            if a['label'].endswith(f'_{organism.upper()}')
        ]
    elif targets_only:
        # Filter to target organisms, exclude vector components
        def is_target(label):
            # Clean up label for matching (remove fragment/partial annotations)
            clean_label = re.sub(r'\s*\(fragment\)', '', label, flags=re.IGNORECASE)
            clean_label = re.sub(r'\s*\(partial\)', '', clean_label, flags=re.IGNORECASE)
            clean_label = clean_label.strip()
            for org in TARGET_ORGANISMS:
                if clean_label.endswith(f'_{org}'):
                    return True
            return False
        protein_annotations = [a for a in protein_annotations if is_target(a['label'])]

    # Verify each annotation
    results = []
    for annotation in protein_annotations:
        result = verify_annotation(annotation)
        results.append(result)

    # Count statuses
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")

    return AnnotationVerificationReport(
        plasmid_name=plasmid_name,
        plasmid_file=os.path.basename(filepath),
        total_cds=len(results),
        passed=passed,
        failed=failed,
        errors=errors,
        results=results,
    )


def format_annotation_report(report: AnnotationVerificationReport, json_output: bool) -> str:
    """Format annotation verification report."""
    if json_output:
        def convert(obj):
            if hasattr(obj, '__dict__'):
                return {k: convert(v) for k, v in obj.__dict__.items() if v is not None}
            elif isinstance(obj, list):
                return [convert(i) for i in obj]
            elif isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj
        return json.dumps(convert(report), indent=2)

    lines = []
    lines.append(f"Annotation Verification Report: {report.plasmid_name}")
    lines.append("=" * 60)
    lines.append(f"File: {report.plasmid_file}")
    lines.append(f"Total CDS annotations: {report.total_cds}")
    lines.append(f"  PASS: {report.passed}")
    lines.append(f"  FAIL: {report.failed}")
    lines.append(f"  ERROR: {report.errors}")
    lines.append("")

    # Results table
    lines.append("Results:")
    lines.append("-" * 60)

    for result in report.results:
        status_icon = "PASS" if result.status == "PASS" else "FAIL" if result.status == "FAIL" else "ERR "
        fragment_flag = " [FRAGMENT]" if result.is_fragment else ""

        if result.uniprot_id:
            lines.append(f"  [{status_icon}] {result.label} ({result.uniprot_id}){fragment_flag}")
            lines.append(f"         Location: {result.location}")
            lines.append(f"         Length: {result.plasmid_length} aa (UniProt: {result.uniprot_length} aa)")
            lines.append(f"         Identity: {result.identity * 100:.1f}%")

            if result.differences:
                lines.append(f"         Differences: {len(result.differences)} shown")
                for diff in result.differences[:5]:
                    lines.append(f"           Pos {diff['position']}: {diff['expected']} -> {diff['observed']}")

            if result.notes:
                lines.append(f"         Note: {result.notes}")
        else:
            lines.append(f"  [{status_icon}] {result.label}{fragment_flag}")
            lines.append(f"         Location: {result.location}")
            if result.error:
                lines.append(f"         Error: {result.error}")

        lines.append("")

    return '\n'.join(lines)


def run_verify_annotations(argv: List[str]) -> int:
    """Run annotation verification mode."""
    parser = argparse.ArgumentParser(
        description="Verify CDS annotations against UniProt reference sequences.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s verify-annotations plasmid.gb
  %(prog)s verify-annotations *.gb --json
  %(prog)s verify-annotations sequencing_results/ --output report.md
        """
    )
    parser.add_argument('files', nargs='+', help='GenBank file(s) or directory with .gb/.gbk files')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--summary', action='store_true', help='Only show summary, not per-protein details')
    parser.add_argument('--targets-only', action='store_true',
                        help='Only verify target proteins (HUMAN, MOUSE, BOVIN), skip vector backbone (ECOLI, ECOLX)')
    parser.add_argument('--organism', '-O', help='Filter to specific organism code (e.g., HUMAN, MOUSE)')

    args = parser.parse_args(argv)

    # Collect input files
    input_files = []
    for path in args.files:
        if os.path.isdir(path):
            for f in os.listdir(path):
                if f.endswith(('.gb', '.gbk')):
                    input_files.append(os.path.join(path, f))
        elif os.path.isfile(path):
            input_files.append(path)
        else:
            print(f"Warning: {path} not found", file=sys.stderr)

    if not input_files:
        print("No input files found", file=sys.stderr)
        return 1

    # Process each file
    all_reports = []
    total_passed = 0
    total_failed = 0
    total_errors = 0

    for filepath in sorted(input_files):
        try:
            report = verify_annotations(filepath, targets_only=args.targets_only, organism=args.organism)
            all_reports.append(report)
            total_passed += report.passed
            total_failed += report.failed
            total_errors += report.errors
        except Exception as e:
            print(f"Error processing {filepath}: {e}", file=sys.stderr)
            continue

    # Format output
    output_lines = []

    if len(all_reports) > 1:
        # Multi-file summary
        output_lines.append("=" * 60)
        output_lines.append("ANNOTATION VERIFICATION SUMMARY")
        output_lines.append("=" * 60)
        output_lines.append(f"Files processed: {len(all_reports)}")
        output_lines.append(f"Total PASS: {total_passed}")
        output_lines.append(f"Total FAIL: {total_failed}")
        output_lines.append(f"Total ERROR: {total_errors}")
        output_lines.append("")

    for report in all_reports:
        if args.summary:
            status = "PASS" if report.failed == 0 and report.errors == 0 else "FAIL"
            output_lines.append(f"[{status}] {report.plasmid_file}: {report.passed}/{report.total_cds} passed")
        else:
            output_lines.append(format_annotation_report(report, args.json))
            output_lines.append("")

    output = '\n'.join(output_lines)

    # Write output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Report written to {args.output}")
    else:
        print(output)

    # Return exit code
    return 0 if total_failed == 0 and total_errors == 0 else 1


# =============================================================================
# Output Formatting
# =============================================================================

def format_report(report: VerificationReport, name: str, json_output: bool) -> str:
    """Format verification report for output."""
    if json_output:
        def convert(obj):
            if hasattr(obj, '__dict__'):
                return {k: convert(v) for k, v in obj.__dict__.items() if v is not None}
            elif isinstance(obj, list):
                return [convert(i) for i in obj]
            elif isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj
        return json.dumps(convert(report), indent=2)

    lines = []
    lines.append(f"ORF Verification Report: {name}")
    lines.append("=" * 50)
    lines.append(f"Status: {report.status.upper()}")

    if report.reason:
        lines.append(f"Reason: {report.reason}")

    if report.placement:
        p = report.placement
        lines.append("")
        lines.append("Placement:")
        lines.append(f"  Strand: {'+' if p.strand == 'plus' else '-'}")
        lines.append(f"  Frame: {p.frame}")
        lines.append(f"  Position: {p.start_nt} - {p.end_nt}")
        lines.append(f"  Length: {p.length_nt} nt ({p.length_nt // 3} aa)")
        if p.wraps_origin:
            lines.append("  Note: ORF wraps around plasmid origin")

    if report.variant:
        v = report.variant
        lines.append("")
        lines.append(f"Amino acid identity: {report.amino_acid_identity * 100:.1f}%")

        if report.discrepancies:
            lines.append("")
            lines.append("Discrepancies:")
            for d in report.discrepancies:
                if isinstance(d, dict):
                    lines.append(f"  Position {d['position'] + 1}: expected {d['expected']}, observed {d['observed']}")
                else:
                    lines.append(f"  Position {d.position + 1}: expected {d.expected}, observed {d.observed}")

        # Show detected tags
        if v.components:
            auto_tags = [c for c in v.components if isinstance(c, dict) and 'Auto-detected' in c.get('name', '')]
            if auto_tags:
                lines.append("")
                lines.append("Auto-detected tags:")
                for tag in auto_tags:
                    lines.append(f"  {tag['name']}: {tag['sequence']}")

    return '\n'.join(lines)


def format_clone_report(report: CloneReport, json_output: bool) -> str:
    if json_output:
        def convert(obj):
            if hasattr(obj, '__dict__'):
                return {k: convert(v) for k, v in obj.__dict__.items() if v is not None}
            if isinstance(obj, list):
                return [convert(i) for i in obj]
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj
        return json.dumps(convert(report), indent=2)

    lines = []
    lines.append(f"Clone Verification Report: {report.sequencing_name}")
    lines.append("=" * 50)
    lines.append(f"Expected: {report.expected_name} ({report.expected_length} bp)")
    lines.append(f"Sequencing: {report.sequencing_name} ({report.sequencing_length} bp)")
    lines.append("")
    lines.append("DNA Alignment:")
    lines.append(f"  Identity: {report.identity * 100:.2f}% ({report.matches}/{report.expected_length} matches)")
    lines.append(f"  Coverage: {report.coverage * 100:.1f}%")
    lines.append(f"  Mismatches: {len(report.mismatches)}")
    lines.append(f"  Insertions: {len(report.insertions)}")
    lines.append(f"  Deletions: {len(report.deletions)}")

    if report.mismatches or report.insertions or report.deletions:
        lines.append("")
        lines.append("Discrepancies:")
        for mismatch in report.mismatches:
            feature = f" (in {mismatch.feature})" if mismatch.feature else ""
            lines.append(f"  Position {mismatch.position}: {mismatch.expected}->{mismatch.observed}{feature}")
        for ins in report.insertions:
            feature = f" (in {ins.feature})" if ins.feature else ""
            lines.append(f"  Position {ins.position}: +{ins.sequence}{feature}")
        for deletion in report.deletions:
            feature = f" (in {deletion.feature})" if deletion.feature else ""
            lines.append(f"  Position {deletion.position}: -{deletion.sequence}{feature}")

    if report.orf_impacts:
        lines.append("")
        lines.append("ORF Analysis:")
        for impact in report.orf_impacts:
            status = "INTACT" if impact.is_intact else "MUTATED"
            lines.append(f"  {impact.name}:")
            lines.append(f"    Status: {status}")
            lines.append(f"    AA Identity: {impact.aa_identity * 100:.1f}%")
            if impact.has_frameshift:
                lines.append("    Note: Frameshift detected")
            if impact.has_premature_stop:
                lines.append("    Note: Premature stop codon detected")
            if impact.aa_changes:
                for change in impact.aa_changes:
                    lines.append(f"    AA {change.position}: {change.expected}->{change.observed}")

    if report.notes:
        lines.append("")
        lines.append("Notes:")
        for note in report.notes:
            lines.append(f"  {note}")

    lines.append("")
    lines.append(f"Overall Status: {report.status.upper()}")
    return '\n'.join(lines)


def list_tags():
    """Print available tag definitions."""
    print("Available Tag Definitions")
    print("=" * 60)
    for tag in TAG_LIBRARY:
        print(f"\n{tag['name']} ({tag['id']})")
        print(f"  Type: {tag.get('kind', 'tag')}")
        print(f"  Description: {tag['description']}")
        for seq in tag.get('sequences', []):
            print(f"  Sequence: {seq}")


def run_verify_clone(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Verify clone sequencing against expected plasmid.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s verify-clone --expected plasmid.gb --sequencing result.seq
  %(prog)s verify-clone --expected plasmid.fasta --sequencing result.ab1 --orf-name GFP --orf-sequence "MSKGEELF..."
        """
    )
    parser.add_argument('--expected', required=True, help='Expected plasmid file (GenBank or FASTA)')
    parser.add_argument('--sequencing', required=True, help='Sequencing result file (.seq, .fasta, .ab1)')
    parser.add_argument('--name', help='Clone identifier for reporting')
    parser.add_argument('--orf-name', help='ORF name (if no GenBank annotations)')
    parser.add_argument('--orf-sequence', help='Expected ORF amino acid sequence')
    parser.add_argument('--max-mismatches', type=int, default=0, help='Maximum allowed DNA mismatches (default: 0)')
    parser.add_argument('--ignore-ends', type=int, default=50, help='Trim N bases at read ends (default: 50)')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')

    args = parser.parse_args(argv)

    try:
        expected_name, expected_seq, features = read_expected_file(args.expected)
        sequencing_name, sequencing_seq = read_sequencing_file(args.sequencing)
    except Exception as e:
        print(f"Error loading input: {e}", file=sys.stderr)
        return 1

    if args.name:
        sequencing_name = args.name

    if args.orf_sequence:
        orf_name = args.orf_name or "ORF"
        orf_sequence = sanitize_aa_sequence(args.orf_sequence)
        features.append(Feature(
            name=orf_name,
            type="CDS",
            start=1,
            end=len(expected_seq),
            strand="+",
            translation=orf_sequence,
        ))

    report = verify_clone(
        expected_name=expected_name,
        expected_seq=expected_seq,
        sequencing_name=sequencing_name,
        sequencing_seq=sequencing_seq,
        features=features,
        max_mismatches=args.max_mismatches,
        ignore_ends=args.ignore_ends,
    )

    print(format_clone_report(report, args.json))
    return 0 if report.status in (CloneStatus.PERFECT.value, CloneStatus.SILENT_MUTATIONS.value, CloneStatus.CONSERVATIVE.value) else 1


# =============================================================================
# Main CLI
# =============================================================================

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "verify-clone":
        return run_verify_clone(sys.argv[2:])

    if len(sys.argv) > 1 and sys.argv[1] == "verify-annotations":
        return run_verify_annotations(sys.argv[2:])

    parser = argparse.ArgumentParser(
        description="Verify open reading frames in plasmid sequences.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --plasmid plasmid.gb --aa-sequence "MHHHHHH..." --name "His-tagged protein"
  %(prog)s --accession MN514974 --aa-sequence "MSKGEELF..." --name "GFP"
  %(prog)s --plasmid plasmid.fasta --aa-sequence "..." --json
  %(prog)s --list-tags
        """
    )

    parser.add_argument('--plasmid', '-p', metavar='FILE',
                        help='Path to plasmid file (FASTA or GenBank format)')
    parser.add_argument('--accession', '-a', metavar='ID',
                        help='NCBI accession number to fetch')
    parser.add_argument('--aa-sequence', '-s', metavar='SEQUENCE',
                        help='Amino acid sequence to verify')
    parser.add_argument('--name', '-n', metavar='NAME', default='Query',
                        help='Name for the ORF (default: Query)')
    parser.add_argument('--allow-alt-start', action='store_true',
                        help='Allow alternative start codons (GTG, TTG)')
    parser.add_argument('--min-identity', type=float, default=1.0, metavar='FLOAT',
                        help='Minimum identity threshold 0-1 (default: 1.0)')
    parser.add_argument('--max-mismatches', type=int, default=0, metavar='INT',
                        help='Maximum allowed amino acid mismatches (default: 0)')
    parser.add_argument('--disallow-internal-met', action='store_true',
                        help='Disallow internal methionine start codons')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')
    parser.add_argument('--list-tags', action='store_true',
                        help='List available tag definitions')

    args = parser.parse_args()

    if args.list_tags:
        list_tags()
        return 0

    if not args.plasmid and not args.accession:
        parser.error("Either --plasmid or --accession is required")

    if not args.aa_sequence:
        parser.error("--aa-sequence is required")

    # Load plasmid sequence
    try:
        if args.plasmid:
            plasmid_name, sequence = read_plasmid_file(args.plasmid)
        else:
            plasmid_name, sequence = fetch_ncbi_sequence(args.accession)
    except Exception as e:
        print(f"Error loading plasmid: {e}", file=sys.stderr)
        return 1

    # Run verification
    report = verify_orf(
        sequence=sequence,
        aa_sequence=args.aa_sequence,
        name=args.name,
        allow_alt_start=args.allow_alt_start,
        min_identity=args.min_identity,
        max_mismatches=args.max_mismatches,
        disallow_internal_met=args.disallow_internal_met,
    )

    # Output results
    output = format_report(report, args.name, args.json)
    print(output)

    # Return exit code based on status
    if report.status == VerificationStatus.VERIFIED.value:
        return 0
    elif report.status == VerificationStatus.INDETERMINATE.value:
        return 2
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
