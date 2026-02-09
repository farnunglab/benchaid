#!/usr/bin/env python3
"""
Protein Parameters CLI - Calculate protein biophysical parameters and generate
purification recommendations.

Calculates molecular weight, isoelectric point, extinction coefficient, and
provides purification strategy recommendations based on detected tags and pI.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


# =============================================================================
# Amino Acid Data
# =============================================================================

# Molecular weights of amino acids (in Daltons)
# Values are for residues (minus water)
AMINO_ACID_WEIGHTS = {
    'A': 89.09,    # Alanine
    'R': 174.20,   # Arginine
    'N': 132.12,   # Asparagine
    'D': 133.10,   # Aspartic acid
    'C': 121.15,   # Cysteine
    'E': 147.13,   # Glutamic acid
    'Q': 146.15,   # Glutamine
    'G': 75.07,    # Glycine
    'H': 155.16,   # Histidine
    'I': 131.17,   # Isoleucine
    'L': 131.17,   # Leucine
    'K': 146.19,   # Lysine
    'M': 149.21,   # Methionine
    'F': 165.19,   # Phenylalanine
    'P': 115.13,   # Proline
    'S': 105.09,   # Serine
    'T': 119.12,   # Threonine
    'W': 204.23,   # Tryptophan
    'Y': 181.19,   # Tyrosine
    'V': 117.15,   # Valine
}

# Water molecular weight (subtracted for peptide bond formation)
WATER_MW = 18.015

# pKa values for isoelectric point calculation
# Format: (pKa, charge at low pH)
PKA_VALUES = {
    'N_TERM': (9.69, 1),     # N-terminus
    'C_TERM': (2.34, -1),    # C-terminus
    'K': (10.54, 1),         # Lysine
    'R': (12.48, 1),         # Arginine
    'H': (6.04, 1),          # Histidine
    'D': (3.90, -1),         # Aspartic acid
    'E': (4.07, -1),         # Glutamic acid
    'C': (8.18, -1),         # Cysteine
    'Y': (10.46, -1),        # Tyrosine
}

# Extinction coefficients at 280nm (M^-1 cm^-1)
# Assuming all Cys residues form cystines (disulfide bonds)
EXTINCTION_COEFFICIENTS = {
    'W': 5500,   # Tryptophan
    'Y': 1490,   # Tyrosine
    'C': 125,    # Cystine (half, per Cys residue when forming disulfide)
}


# =============================================================================
# Tag and Cleavage Site Definitions
# =============================================================================

TAG_DEFINITIONS = [
    {
        "id": "his6",
        "name": "His6",
        "kind": "affinity",
        "sequences": ["HHHHHH", "MHHHHHH", "MGSSHHHHH"],  # Include M- prefixed versions for N-terminal
        "description": "Polyhistidine tag for Ni-NTA/IMAC purification",
        "column": "HisTrap",
    },
    {
        "id": "his10",
        "name": "His10",
        "kind": "affinity",
        "sequences": ["HHHHHHHHHH"],
        "description": "Extended polyhistidine tag for stronger binding",
        "column": "HisTrap",
    },
    {
        "id": "mbp",
        "name": "MBP",
        "kind": "solubility",
        "sequences": [
            "MKIEEGKLVIWINGDKGYNGLAEVGKKFEKDTGIKVTVEHPDKLEEKFPQVAATGDGPDIIFWAHDRFGGYAQSGLLAEITPDKAFQDKLYPFTWDAVRYNGKLIAYPIAVEALSLIYNKDLLPNPPKTWEEIPALDKELKAKGKSALMFNLQEPYFTWPLIAADGGYAFKYENGKYDIKDVGVDNAGAKAGLTFLVDLIKNKHMNADTDYSIAEAAFNKGETAMTINGPWAWSNIDTSKVNYGVTVLPTFKGQPSKPFVGVLSAGINAASPNKELAKEFLENYLLTDEGLEAVNKDKPLGAVALKSYEEELAKDPRIAATMENAQKGEIMPNIPQMSAFWYAVRTAVINAASGRQTVDEALKDAQT"
        ],
        "description": "Maltose Binding Protein for solubility enhancement",
        "column": "Amylose",
        "min_identity": 0.9,  # Allow some sequence variation
    },
    {
        "id": "gst",
        "name": "GST",
        "kind": "affinity",
        "sequences": [
            "MSPILGYWKIKGLVQPTRLLLEYLEEKYEEHLYERDEGDKWRNKKFELGLEFPNLPYYIDGDVKLTQSMAIIRYIADKHNMLGGCPKERAEISMLEGAVLDIRYGVSRIAYSKDFETLKVDFLSKLPEMLKMFEDRLCHKTYLNGDHVTHPDFMLYDALDVVLYMDPMCLDAFPKLVCFKKRIEAIPQIDKYLKSSKYIAWPLQGWQATFGGGDHPPKSDLVPRGS"
        ],
        "description": "Glutathione S-Transferase tag",
        "column": "GSTrap",
        "min_identity": 0.85,
    },
    {
        "id": "sumo",
        "name": "SUMO",
        "kind": "solubility",
        "sequences": [
            "MGSSHHHHHHGSDSEVNQEAKPEVKPEVKPETHINLKVSDGSSEIFFKIKKTTPLRRLMEAFAKRQGKEMDSLRFLYDGIRIQADQTPEDLDMEDNDIIEAHREQIGG"
        ],
        "description": "SUMO tag for enhanced solubility (cleaved by Ulp1/SUMO protease)",
        "column": "HisTrap",
        "min_identity": 0.85,
    },
    {
        "id": "strep",
        "name": "Strep-tag II",
        "kind": "affinity",
        "sequences": ["WSHPQFEK"],
        "description": "Strep-Tactin affinity tag",
        "column": "StrepTrap",
    },
    {
        "id": "flag",
        "name": "FLAG",
        "kind": "affinity",
        "sequences": ["DYKDDDDK"],
        "description": "FLAG epitope tag",
        "column": "Anti-FLAG",
    },
]

CLEAVAGE_SITES = [
    {
        "id": "tev",
        "name": "TEV protease",
        "sequences": ["ENLYFQS", "ENLYFQG"],
        "cleavage_position": 6,  # Cleaves after Q
        "description": "Tobacco Etch Virus protease site (cleaves after ENLYFQ)",
    },
    {
        "id": "3c",
        "name": "3C/PreScission protease",
        "sequences": ["LEVLFQGP"],
        "cleavage_position": 6,  # Cleaves after Q
        "description": "HRV 3C protease site (cleaves after LEVLFQ)",
    },
    {
        "id": "thrombin",
        "name": "Thrombin",
        "sequences": ["LVPRGS"],
        "cleavage_position": 4,  # Cleaves after R
        "description": "Thrombin cleavage site (cleaves after LVPR)",
    },
    {
        "id": "enterokinase",
        "name": "Enterokinase",
        "sequences": ["DDDDK"],
        "cleavage_position": 5,  # Cleaves after K
        "description": "Enterokinase cleavage site (cleaves after DDDDK)",
    },
]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AminoAcidCount:
    """Count of each amino acid in the sequence."""
    counts: Dict[str, int] = field(default_factory=dict)
    total: int = 0


@dataclass
class DetectedTag:
    """Information about a detected tag."""
    name: str
    kind: str
    position: str  # "N-terminal", "C-terminal", or "internal"
    start: int
    end: int
    sequence: str
    column: Optional[str] = None


@dataclass
class DetectedCleavageSite:
    """Information about a detected cleavage site."""
    name: str
    position: int
    sequence: str
    cleavage_position: int
    cleaved_product_start: int


@dataclass
class ProteinParameters:
    """Calculated protein parameters."""
    sequence_length: int
    molecular_weight: float
    isoelectric_point: float
    extinction_coefficient: int
    extinction_coefficient_reduced: int
    absorbance_01_percent: float
    absorbance_01_percent_reduced: float
    amino_acid_counts: Dict[str, int]


@dataclass
class CleavedProteinParameters:
    """Parameters for cleaved protein product."""
    cleavage_site: str
    cleaved_sequence: str
    sequence_length: int
    molecular_weight: float
    isoelectric_point: float
    extinction_coefficient: int
    absorbance_01_percent: float


@dataclass
class PurificationRecommendation:
    """Purification strategy recommendation."""
    affinity_column: Optional[str]
    ion_exchange: Optional[str]
    concentrator_mwco: str
    size_exclusion_column: str
    cleavage_strategy: Optional[str]
    notes: List[str]


@dataclass
class ProtParamReport:
    """Complete protein parameters report."""
    parameters: ProteinParameters
    detected_tags: List[DetectedTag]
    detected_cleavage_sites: List[DetectedCleavageSite]
    cleaved_parameters: Optional[CleavedProteinParameters]
    purification: Optional[PurificationRecommendation]


# =============================================================================
# Sequence Utilities
# =============================================================================

def sanitize_sequence(seq: str) -> str:
    """Clean and validate amino acid sequence."""
    sanitized = []
    valid_aa = set(AMINO_ACID_WEIGHTS.keys())

    for ch in seq:
        if ch.isspace():
            continue
        upper = ch.upper()
        if upper in valid_aa:
            sanitized.append(upper)
        elif upper == 'X':
            # Unknown amino acid, skip
            continue
        elif upper == '*':
            # Stop codon, skip
            continue
        elif upper.isdigit():
            # Skip numbers
            continue
        elif upper.isalpha():
            raise ValueError(f"Invalid amino acid: {ch}")

    return ''.join(sanitized)


def count_amino_acids(sequence: str) -> Dict[str, int]:
    """Count occurrences of each amino acid."""
    counts = {aa: 0 for aa in AMINO_ACID_WEIGHTS.keys()}
    for aa in sequence:
        if aa in counts:
            counts[aa] += 1
    return counts


# =============================================================================
# Protein Parameter Calculations
# =============================================================================

def calculate_molecular_weight(sequence: str) -> float:
    """
    Calculate molecular weight of a protein sequence.

    MW = sum(residue weights) - (n-1) * water_weight
    """
    if not sequence:
        return 0.0

    total = 0.0
    for aa in sequence:
        total += AMINO_ACID_WEIGHTS.get(aa, 0)

    # Subtract water for each peptide bond (n-1 bonds for n residues)
    total -= (len(sequence) - 1) * WATER_MW

    return round(total, 2)


def calculate_charge_at_ph(sequence: str, ph: float, counts: Dict[str, int]) -> float:
    """Calculate the net charge of a protein at a given pH."""
    charge = 0.0

    # N-terminus contribution
    pka, base_charge = PKA_VALUES['N_TERM']
    if base_charge > 0:
        charge += base_charge / (1 + 10 ** (ph - pka))
    else:
        charge += base_charge / (1 + 10 ** (pka - ph))

    # C-terminus contribution
    pka, base_charge = PKA_VALUES['C_TERM']
    if base_charge > 0:
        charge += base_charge / (1 + 10 ** (ph - pka))
    else:
        charge += base_charge / (1 + 10 ** (pka - ph))

    # Charged amino acid contributions
    for aa in ['K', 'R', 'H', 'D', 'E', 'C', 'Y']:
        if aa in PKA_VALUES:
            pka, base_charge = PKA_VALUES[aa]
            count = counts.get(aa, 0)
            if count > 0:
                if base_charge > 0:
                    charge += count * base_charge / (1 + 10 ** (ph - pka))
                else:
                    charge += count * base_charge / (1 + 10 ** (pka - ph))

    return charge


def calculate_isoelectric_point(sequence: str) -> float:
    """
    Calculate the isoelectric point (pI) of a protein.

    Uses bisection method to find pH where net charge is zero.
    """
    if not sequence:
        return 7.0

    counts = count_amino_acids(sequence)

    # Bisection method
    ph_low = 0.0
    ph_high = 14.0
    tolerance = 0.01

    while (ph_high - ph_low) > tolerance:
        ph_mid = (ph_low + ph_high) / 2
        charge = calculate_charge_at_ph(sequence, ph_mid, counts)

        if charge > 0:
            ph_low = ph_mid
        else:
            ph_high = ph_mid

    return round((ph_low + ph_high) / 2, 1)


def calculate_extinction_coefficient(sequence: str, reduced: bool = False) -> int:
    """
    Calculate molar extinction coefficient at 280nm.

    Using the Pace method:
    E280 = (#Trp * 5500) + (#Tyr * 1490) + (#Cystine * 125)

    Args:
        sequence: Amino acid sequence
        reduced: If True, assume all Cys are reduced (no disulfide bonds)
    """
    counts = count_amino_acids(sequence)

    ext_coef = 0
    ext_coef += counts.get('W', 0) * EXTINCTION_COEFFICIENTS['W']
    ext_coef += counts.get('Y', 0) * EXTINCTION_COEFFICIENTS['Y']

    if not reduced:
        # Assume all Cys form cystines (disulfide bonds)
        # Each cystine (pair of Cys) contributes 125
        num_cystines = counts.get('C', 0) // 2
        ext_coef += num_cystines * EXTINCTION_COEFFICIENTS['C'] * 2

    return ext_coef


def calculate_absorbance_01_percent(extinction_coefficient: int, molecular_weight: float) -> float:
    """
    Calculate absorbance of a 0.1% (1 g/L) solution.

    A = E / MW
    where E is the extinction coefficient and MW is molecular weight.
    """
    if molecular_weight <= 0:
        return 0.0
    return round(extinction_coefficient / molecular_weight, 3)


def calculate_parameters(sequence: str) -> ProteinParameters:
    """Calculate all protein parameters."""
    sequence = sanitize_sequence(sequence)
    counts = count_amino_acids(sequence)
    mw = calculate_molecular_weight(sequence)
    pi = calculate_isoelectric_point(sequence)
    ext_coef = calculate_extinction_coefficient(sequence, reduced=False)
    ext_coef_red = calculate_extinction_coefficient(sequence, reduced=True)
    abs_01 = calculate_absorbance_01_percent(ext_coef, mw)
    abs_01_red = calculate_absorbance_01_percent(ext_coef_red, mw)

    return ProteinParameters(
        sequence_length=len(sequence),
        molecular_weight=mw,
        isoelectric_point=pi,
        extinction_coefficient=ext_coef,
        extinction_coefficient_reduced=ext_coef_red,
        absorbance_01_percent=abs_01,
        absorbance_01_percent_reduced=abs_01_red,
        amino_acid_counts=counts,
    )


# =============================================================================
# Tag and Cleavage Site Detection
# =============================================================================

def sequence_identity(seq1: str, seq2: str) -> float:
    """Calculate sequence identity between two sequences."""
    if len(seq1) != len(seq2):
        return 0.0
    if not seq1:
        return 1.0
    matches = sum(1 for a, b in zip(seq1, seq2) if a == b)
    return matches / len(seq1)


def detect_tags(sequence: str) -> List[DetectedTag]:
    """Detect known affinity and solubility tags in the sequence."""
    detected = []
    seq_len = len(sequence)

    for tag_def in TAG_DEFINITIONS:
        min_identity = tag_def.get('min_identity', 1.0)

        for tag_seq in tag_def['sequences']:
            tag_len = len(tag_seq)

            # Check N-terminal region
            if seq_len >= tag_len:
                n_term_region = sequence[:tag_len]
                if sequence_identity(n_term_region, tag_seq) >= min_identity:
                    detected.append(DetectedTag(
                        name=tag_def['name'],
                        kind=tag_def['kind'],
                        position="N-terminal",
                        start=0,
                        end=tag_len,
                        sequence=n_term_region,
                        column=tag_def.get('column'),
                    ))
                    continue

            # Check C-terminal region
            if seq_len >= tag_len:
                c_term_region = sequence[-tag_len:]
                if sequence_identity(c_term_region, tag_seq) >= min_identity:
                    detected.append(DetectedTag(
                        name=tag_def['name'],
                        kind=tag_def['kind'],
                        position="C-terminal",
                        start=seq_len - tag_len,
                        end=seq_len,
                        sequence=c_term_region,
                        column=tag_def.get('column'),
                    ))
                    continue

            # Check for internal occurrence (for smaller tags only)
            if tag_len <= 20:
                idx = sequence.find(tag_seq)
                if idx > 0 and idx + tag_len < seq_len:
                    detected.append(DetectedTag(
                        name=tag_def['name'],
                        kind=tag_def['kind'],
                        position="internal",
                        start=idx,
                        end=idx + tag_len,
                        sequence=tag_seq,
                        column=tag_def.get('column'),
                    ))

    return detected


def detect_cleavage_sites(sequence: str) -> List[DetectedCleavageSite]:
    """Detect known protease cleavage sites in the sequence."""
    detected = []

    for site_def in CLEAVAGE_SITES:
        for site_seq in site_def['sequences']:
            idx = sequence.find(site_seq)
            if idx >= 0:
                cleavage_pos = idx + site_def['cleavage_position']
                detected.append(DetectedCleavageSite(
                    name=site_def['name'],
                    position=idx,
                    sequence=site_seq,
                    cleavage_position=site_def['cleavage_position'],
                    cleaved_product_start=cleavage_pos,
                ))

    return detected


def calculate_cleaved_parameters(
    sequence: str,
    cleavage_sites: List[DetectedCleavageSite]
) -> Optional[CleavedProteinParameters]:
    """Calculate parameters for the cleaved protein product."""
    if not cleavage_sites:
        return None

    # Use the first (most N-terminal) cleavage site
    site = min(cleavage_sites, key=lambda s: s.cleaved_product_start)
    cleaved_sequence = sequence[site.cleaved_product_start:]

    if not cleaved_sequence:
        return None

    mw = calculate_molecular_weight(cleaved_sequence)
    pi = calculate_isoelectric_point(cleaved_sequence)
    ext_coef = calculate_extinction_coefficient(cleaved_sequence, reduced=False)
    abs_01 = calculate_absorbance_01_percent(ext_coef, mw)

    return CleavedProteinParameters(
        cleavage_site=site.name,
        cleaved_sequence=cleaved_sequence[:50] + "..." if len(cleaved_sequence) > 50 else cleaved_sequence,
        sequence_length=len(cleaved_sequence),
        molecular_weight=mw,
        isoelectric_point=pi,
        extinction_coefficient=ext_coef,
        absorbance_01_percent=abs_01,
    )


# =============================================================================
# Purification Recommendations
# =============================================================================

def generate_purification_recommendations(
    parameters: ProteinParameters,
    cleaved_params: Optional[CleavedProteinParameters],
    tags: List[DetectedTag],
    cleavage_sites: List[DetectedCleavageSite],
) -> PurificationRecommendation:
    """Generate purification strategy recommendations."""
    notes = []

    # Determine affinity column based on detected tags
    affinity_columns = []
    for tag in tags:
        if tag.column and tag.column not in affinity_columns:
            affinity_columns.append(tag.column)

    affinity_column = None
    if affinity_columns:
        if "HisTrap" in affinity_columns:
            affinity_column = "HisTrap (Ni-NTA/IMAC)"
            notes.append("His tag detected - use HisTrap for initial capture")
        elif "Amylose" in affinity_columns:
            affinity_column = "Amylose"
            notes.append("MBP tag detected - use Amylose column")
        elif "GSTrap" in affinity_columns:
            affinity_column = "GSTrap"
            notes.append("GST tag detected - use GSTrap column")
        elif "StrepTrap" in affinity_columns:
            affinity_column = "StrepTrap"
            notes.append("Strep tag detected - use StrepTrap column")
        else:
            affinity_column = affinity_columns[0]

    # Multiple tags - suggest tandem purification
    if len(affinity_columns) > 1:
        notes.append(f"Multiple tags detected: {', '.join(affinity_columns)}")
        notes.append("Consider tandem affinity purification for higher purity")

    # Cleavage strategy
    cleavage_strategy = None
    if cleavage_sites:
        site_names = [s.name for s in cleavage_sites]
        cleavage_strategy = f"Cleave with {site_names[0]}"
        if "TEV" in site_names[0]:
            notes.append("TEV site detected - cleave tags with TEV protease")
            notes.append("Follow cleavage with reverse IMAC (OrthoNi) to remove uncleaved protein")
        elif "3C" in site_names[0]:
            notes.append("3C site detected - cleave tags with 3C/PreScission protease")
        elif "Thrombin" in site_names[0]:
            notes.append("Thrombin site detected - cleave tags with thrombin")

    # Ion exchange recommendation based on pI of cleaved product
    # Use cleaved pI if available, otherwise use full protein pI
    working_pi = cleaved_params.isoelectric_point if cleaved_params else parameters.isoelectric_point
    working_mw = cleaved_params.molecular_weight if cleaved_params else parameters.molecular_weight

    ion_exchange = None
    if working_pi < 6.5:
        ion_exchange = "Q column (anion exchange)"
        notes.append(f"pI = {working_pi} (< 6.5) - protein is acidic, use Q column at pH 7-8")
    elif working_pi > 8.5:
        ion_exchange = "S column (cation exchange)"
        notes.append(f"pI = {working_pi} (> 8.5) - protein is basic, use S column at pH 6-7")
    else:
        notes.append(f"pI = {working_pi} - near neutral, ion exchange may be challenging")
        notes.append("Consider using Q at pH 8.5+ or S at pH 5.5-")

    # Concentrator MWCO recommendation
    if working_mw <= 20000:
        concentrator = "3K MWCO"
    elif working_mw <= 60000:
        concentrator = "10K MWCO"
    elif working_mw <= 100000:
        concentrator = "30K MWCO"
    elif working_mw <= 200000:
        concentrator = "50K MWCO"
    else:
        concentrator = "100K MWCO"

    # Size exclusion column recommendation
    if working_mw <= 65000:
        sec_column = "Superdex 75 (S75)"
        notes.append(f"MW = {working_mw/1000:.1f} kDa - use S75 for optimal resolution")
    elif working_mw <= 200000:
        sec_column = "Superdex 200 (S200)"
        notes.append(f"MW = {working_mw/1000:.1f} kDa - use S200 for optimal resolution")
    else:
        sec_column = "Superose 6"
        notes.append(f"MW = {working_mw/1000:.1f} kDa - use Superose 6 for large proteins")

    return PurificationRecommendation(
        affinity_column=affinity_column,
        ion_exchange=ion_exchange,
        concentrator_mwco=concentrator,
        size_exclusion_column=sec_column,
        cleavage_strategy=cleavage_strategy,
        notes=notes,
    )


# =============================================================================
# Main Analysis Function
# =============================================================================

def analyze_protein(
    sequence: str,
    include_purification: bool = False,
) -> ProtParamReport:
    """
    Perform complete protein analysis.

    Args:
        sequence: Amino acid sequence
        include_purification: Whether to include purification recommendations

    Returns:
        Complete protein parameters report
    """
    sequence = sanitize_sequence(sequence)

    # Calculate basic parameters
    parameters = calculate_parameters(sequence)

    # Detect tags and cleavage sites
    tags = detect_tags(sequence)
    cleavage_sites = detect_cleavage_sites(sequence)

    # Calculate cleaved protein parameters
    cleaved_params = calculate_cleaved_parameters(sequence, cleavage_sites)

    # Generate purification recommendations if requested
    purification = None
    if include_purification:
        purification = generate_purification_recommendations(
            parameters, cleaved_params, tags, cleavage_sites
        )

    return ProtParamReport(
        parameters=parameters,
        detected_tags=tags,
        detected_cleavage_sites=cleavage_sites,
        cleaved_parameters=cleaved_params,
        purification=purification,
    )


# =============================================================================
# Output Formatting
# =============================================================================

def format_report(report: ProtParamReport, json_output: bool = False) -> str:
    """Format the protein parameters report for output."""
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
    p = report.parameters

    lines.append("=" * 60)
    lines.append("PROTEIN PARAMETERS")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Number of amino acids: {p.sequence_length}")
    lines.append(f"Molecular weight:      {p.molecular_weight:.2f} Da ({p.molecular_weight/1000:.2f} kDa)")
    lines.append(f"Theoretical pI:        {p.isoelectric_point}")
    lines.append("")
    lines.append("Extinction coefficient at 280nm (M-1 cm-1):")
    lines.append(f"  All Cys form cystines: {p.extinction_coefficient}")
    lines.append(f"  All Cys reduced:       {p.extinction_coefficient_reduced}")
    lines.append("")
    lines.append("Absorbance 0.1% (1 g/L):")
    lines.append(f"  All Cys form cystines: {p.absorbance_01_percent}")
    lines.append(f"  All Cys reduced:       {p.absorbance_01_percent_reduced}")

    # Detected tags
    if report.detected_tags:
        lines.append("")
        lines.append("-" * 60)
        lines.append("DETECTED TAGS")
        lines.append("-" * 60)
        for tag in report.detected_tags:
            lines.append(f"  {tag.name} ({tag.kind}) - {tag.position}")
            if tag.column:
                lines.append(f"    Suggested column: {tag.column}")

    # Detected cleavage sites
    if report.detected_cleavage_sites:
        lines.append("")
        lines.append("-" * 60)
        lines.append("DETECTED CLEAVAGE SITES")
        lines.append("-" * 60)
        for site in report.detected_cleavage_sites:
            lines.append(f"  {site.name} at position {site.position + 1}")
            lines.append(f"    Sequence: {site.sequence}")

    # Cleaved protein parameters
    if report.cleaved_parameters:
        cp = report.cleaved_parameters
        lines.append("")
        lines.append("-" * 60)
        lines.append(f"CLEAVED PRODUCT (after {cp.cleavage_site})")
        lines.append("-" * 60)
        lines.append(f"  Length:       {cp.sequence_length} aa")
        lines.append(f"  MW:           {cp.molecular_weight:.2f} Da ({cp.molecular_weight/1000:.2f} kDa)")
        lines.append(f"  pI:           {cp.isoelectric_point}")
        lines.append(f"  Ext. coef:    {cp.extinction_coefficient}")
        lines.append(f"  Abs 0.1%:     {cp.absorbance_01_percent}")

    # Purification recommendations
    if report.purification:
        rec = report.purification
        lines.append("")
        lines.append("=" * 60)
        lines.append("PURIFICATION RECOMMENDATIONS")
        lines.append("=" * 60)
        if rec.affinity_column:
            lines.append(f"Affinity column:    {rec.affinity_column}")
        if rec.cleavage_strategy:
            lines.append(f"Tag cleavage:       {rec.cleavage_strategy}")
        if rec.ion_exchange:
            lines.append(f"Ion exchange:       {rec.ion_exchange}")
        lines.append(f"Concentrator:       {rec.concentrator_mwco}")
        lines.append(f"Size exclusion:     {rec.size_exclusion_column}")

        if rec.notes:
            lines.append("")
            lines.append("Notes:")
            for note in rec.notes:
                lines.append(f"  - {note}")

    lines.append("")
    return '\n'.join(lines)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Calculate protein biophysical parameters and generate purification recommendations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --sequence MKTAYIAKQRQISFVKSH...
  %(prog)s --sequence MHHHHHH... --purification
  %(prog)s --sequence MKTAYIAK... --json
        """
    )

    parser.add_argument('--sequence', '-s', metavar='SEQUENCE', required=True,
                        help='Amino acid sequence in single letter code')
    parser.add_argument('--purification', '-p', action='store_true',
                        help='Include purification recommendations')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')

    args = parser.parse_args()

    try:
        report = analyze_protein(
            sequence=args.sequence,
            include_purification=args.purification,
        )

        output = format_report(report, args.json)
        print(output)
        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
