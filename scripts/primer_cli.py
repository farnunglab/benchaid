#!/usr/bin/env python3
"""
Primer Designer CLI - Non-interactive wrapper for primer design.

Designs PCR primers for LIC cloning, sequencing, and Gibson/HiFi assembly using Primer3.
"""

import argparse
import glob
import json
import os
import re
import sys
import textwrap

try:
    import primer3
    from primer3 import calc_tm
except ImportError:
    print("Error: primer3-py is required. Install with: pip install primer3-py", file=sys.stderr)
    sys.exit(1)

try:
    from Bio import SeqIO, Entrez
    from Bio.Restriction import SwaI, PmeI
    from Bio.Seq import Seq
except ImportError:
    print("Error: BioPython is required. Install with: pip install biopython", file=sys.stderr)
    sys.exit(1)

# Import settings from local settings.py
try:
    from settings import (
        sequence_dictionary,
        global_arg_dictionary_sequencing,
        global_arg_dictionary_lic,
        global_arg_dictionary_gibson,
        email_address,
        initials
    )
except ImportError:
    # Default settings if settings.py not available
    email_address = 'user@example.com'
    initials = 'XX'
    sequence_dictionary = {'SEQUENCE_ID': 'Query', 'SEQUENCE_TEMPLATE': None}
    global_arg_dictionary_lic = {
        'PRIMER_TASK': 'pick_cloning_primers',
        'PRIMER_PICK_LEFT_PRIMER': 1,
        'PRIMER_PICK_RIGHT_PRIMER': 1,
        'PRIMER_PICK_INTERNAL_OLIGO': 0,
        'PRIMER_MIN_SIZE': 25,
        'PRIMER_OPT_SIZE': 30,
        'PRIMER_MAX_SIZE': 35,
        'PRIMER_MIN_TM': 60.0,
        'PRIMER_OPT_TM': 61.0,
        'PRIMER_MAX_TM': 62.0,
        'PRIMER_NUM_RETURN': 5,
        'PRIMER_PICK_ANYWAY': 1,
    }
    global_arg_dictionary_sequencing = {
        'PRIMER_TASK': 'pick_sequencing_primers',
        'PRIMER_PICK_LEFT_PRIMER': 1,
        'PRIMER_PICK_RIGHT_PRIMER': 1,
        'PRIMER_PICK_INTERNAL_OLIGO': 0,
        'PRIMER_MIN_SIZE': 18,
        'PRIMER_OPT_SIZE': 20,
        'PRIMER_MAX_SIZE': 25,
        'PRIMER_MIN_TM': 57.0,
        'PRIMER_OPT_TM': 59.0,
        'PRIMER_MAX_TM': 62.0,
        'PRIMER_NUM_RETURN': 30,
        'PRIMER_SEQUENCING_SPACING': 750,
        'PRIMER_SEQUENCING_INTERVAL': 300,
        'PRIMER_SEQUENCING_LEAD': 80,
        'PRIMER_SEQUENCING_ACCURACY': 30,
    }
    global_arg_dictionary_gibson = {
        'PRIMER_TASK': 'pick_cloning_primers',
        'PRIMER_PICK_LEFT_PRIMER': 0,
        'PRIMER_PICK_RIGHT_PRIMER': 1,
        'PRIMER_PICK_INTERNAL_OLIGO': 0,
        'PRIMER_MIN_SIZE': 25,
        'PRIMER_OPT_SIZE': 30,
        'PRIMER_MAX_SIZE': 35,
        'PRIMER_MIN_TM': 60.0,
        'PRIMER_OPT_TM': 61.0,
        'PRIMER_MAX_TM': 62.0,
        'PRIMER_NUM_RETURN': 5,
        'PRIMER_PICK_ANYWAY': 1,
    }


# LIC overhang sequences - MacroLab vectors v8
# See: MacroLab_Vectors_Summary_v8.xlsx
LIC_TAGS = {
    # v1: N-terminal tagged constructs (His6-MBP, His6-GST, etc.) - no ATG in ORF
    "v1": {
        "forward": "TACTTCCAATCCAATGCA",
        "reverse": "TTATCCACTTCCAATGTTATTA",
        "orf_needs_atg": False,
        "orf_needs_stop": False,
        "description": "N-terminal tags (1B, 1C, 1M, 2BT, 2CT, 4B, 4C, etc.)",
    },
    # v2: Untagged constructs - ORF needs ATG
    "v2": {
        "forward": "TTTAAGAAGGAGATATAGATC",
        "reverse": "TTATGGAGTTGGGATCTTATTA",
        "orf_needs_atg": True,
        "orf_needs_stop": False,
        "description": "Untagged (2AT, etc.) - ORF needs ATG",
    },
    # v3: C-terminal tagged constructs - ORF needs ATG
    "v3": {
        "forward": "TTTAAGAAGGAGATATAGTTC",
        "reverse": "GGATTGGAAGTAGAGGTTCTC",
        "orf_needs_atg": True,
        "orf_needs_stop": False,
        "description": "C-terminal tags (2Bc-T, 2Cc-T, etc.) - ORF needs ATG",
    },
    # vKoz: Kozak sequence for eukaryotic expression - ORF needs ATG
    "vKoz": {
        "forward": "TACTTCCAATCCAATGCCACC",
        "reverse": "TTATCCACTTCCAATGTTATTA",  # uses v1 reverse
        "orf_needs_atg": True,
        "orf_needs_stop": False,
        "description": "Kozak sequence - ORF needs ATG",
    },
    # vBac: Baculovirus insect expression - ORF needs ATG
    "vBac": {
        "forward": "TACTTCCAATCCAATCG",
        "reverse": "TTATCCACTTCCAATGTTATTA",  # uses v1 reverse
        "orf_needs_atg": True,
        "orf_needs_stop": False,
        "description": "Baculovirus (4A, 5A) - ORF needs ATG",
    },
    # vGFP1: C-terminal fluorescent protein fusion with v1 forward
    "vGFP1": {
        "forward": "TACTTCCAATCCAATGCA",  # uses v1 forward
        "reverse": "CTCCCACTACCAATGCC",
        "orf_needs_atg": False,
        "orf_needs_stop": False,
        "description": "C-terminal FP (MBP-mCherry, etc.) - no stop codon",
    },
    # vGFP2: C-terminal fluorescent protein fusion with v2 forward
    "vGFP2": {
        "forward": "TTTAAGAAGGAGATATAGATC",  # uses v2 forward
        "reverse": "GTTGGAGGATGAGAGGATCCC",
        "orf_needs_atg": True,
        "orf_needs_stop": False,
        "description": "Untagged C-terminal FP (u-mCherry, etc.) - ORF needs ATG",
    },
    # SLIC vHRV: HRV 3C protease site SLIC cloning
    "vHRV": {
        "forward": "GTGCTGTTCCAGGGTCCGAAT",
        "reverse": "TGGTGGTGGTGGTGCTCGATTA",
        "orf_needs_atg": False,
        "orf_needs_stop": False,
        "description": "HRV 3C protease SLIC cloning",
    },
}

# Default to v1 for backwards compatibility
LIC_FORWARD_OVERHANG = LIC_TAGS["v1"]["forward"]
LIC_REVERSE_OVERHANG = LIC_TAGS["v1"]["reverse"]

# Vector to LIC tag mapping
VECTOR_LIC_MAPPING = {
    # Series 1: E.coli T7 (N-terminal tags)
    "1B": "v1", "1C": "v1", "1G": "v1", "1GFP": "v1", "1L": "v1", "1M": "v1",
    "1N": "v1", "1O": "v1", "1P": "v1", "1R": "v1", "1S": "v1", "1X": "v1",
    # Series 2: E.coli T7
    "2AT": "v2",  # Untagged
    "2BT": "v1", "2CT": "v1", "2CT-10": "v1", "2GT": "v1", "2GFP-T": "v1",
    "2J-T": "v1", "2K-T": "v1", "2LT": "v1", "2MT": "v1", "2NT": "v1",
    "2NTL": "v1", "2OT": "v1", "2PT": "v1", "2RT": "v1", "2RRT": "v1",
    "2HRT": "v1", "2ST": "v1", "2TT": "v1", "2U-T": "v1", "2XT": "v1",
    # Series 2c: C-terminal tags
    "2Bc-T": "v3", "2Cc-T": "v3", "2Oc-T": "v3", "2Tc-T": "v3",
    # Series 4: SF9 Insect
    "4A": "vBac", "4B": "v1", "4C": "v1",
    # Series 5: SF9 Insect (polycistronic)
    "5A": "vBac", "5B": "v1", "5C": "v1",
    # 438 series (aliases for 4-series)
    "438-A": "vBac", "438-B": "v1", "438-C": "v1",
    # Fluorescent protein fusions
    "MBP-mCherry": "vGFP1", "H6-mCherry": "vGFP1", "u-mCherry": "vGFP2",
    "MBP-mOrange": "vGFP1", "H6-mOrange": "vGFP1", "u-mOrange": "vGFP2",
    "MBP-mCitrine": "vGFP1", "H6-mCitrine": "vGFP1", "u-mCitrine": "vGFP2",
    "MBP-msfGFP": "vGFP1", "H6-msfGFP": "vGFP1", "u-msfGFP": "vGFP2",
    "MBP-mCerulean": "vGFP1", "H6-mCerulean": "vGFP1", "u-mCerulean": "vGFP2",
}

# Default vectors directory
VECTORS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vectors")


def calculate_overlap_tm(sequence: str) -> float:
    """Calculate Tm for an overlap sequence using nearest-neighbor method."""
    return calc_tm(sequence, mv_conc=50, dv_conc=1.5, dntp_conc=0.2)


def find_overlap_for_tm(sequence: str, start_pos: int, direction: str, target_tm: float,
                        min_len: int = 15, max_len: int = 60) -> tuple:
    """
    Find an overlap region that achieves the target Tm.

    Args:
        sequence: Full sequence to extract overlap from
        start_pos: Starting position for the overlap
        direction: 'forward' (extend right) or 'reverse' (extend left)
        target_tm: Target melting temperature
        min_len: Minimum overlap length
        max_len: Maximum overlap length

    Returns:
        tuple: (overlap_sequence, actual_tm, length)
    """
    best_overlap = None
    best_tm = 0
    best_len = 0

    for length in range(min_len, max_len + 1):
        if direction == 'forward':
            # Extend to the right from start_pos
            if start_pos + length > len(sequence):
                break
            overlap = sequence[start_pos:start_pos + length]
        else:
            # Extend to the left from start_pos
            if start_pos - length < 0:
                break
            overlap = sequence[start_pos - length:start_pos]

        tm = calculate_overlap_tm(overlap)

        # Store best result
        if best_overlap is None or abs(tm - target_tm) < abs(best_tm - target_tm):
            best_overlap = overlap
            best_tm = tm
            best_len = length

        # If we've reached or exceeded target, we're done
        if tm >= target_tm:
            return overlap, tm, length

    return best_overlap, best_tm, best_len


def load_vector(vector_name: str) -> dict:
    """
    Load a vector from the vectors directory or a file path.

    Returns dict with:
        - name: vector name
        - sequence: full sequence
        - insert_site: position where insert goes
        - upstream_seq: sequence before insert site
        - downstream_seq: sequence after insert site
    """
    # Check if it's a file path
    if os.path.isfile(vector_name):
        vector_path = vector_name
        name = os.path.splitext(os.path.basename(vector_name))[0]
    else:
        # Look in vectors directory
        vector_path = os.path.join(VECTORS_DIR, f"{vector_name}.gb")
        if not os.path.exists(vector_path):
            # Try without .gb extension
            matches = glob.glob(os.path.join(VECTORS_DIR, f"{vector_name}*"))
            if matches:
                vector_path = matches[0]
            else:
                raise FileNotFoundError(f"Vector '{vector_name}' not found in {VECTORS_DIR}")
        name = vector_name

    # Parse GenBank file
    record = SeqIO.read(vector_path, "genbank")
    sequence = str(record.seq).upper()

    # Find insertion site by looking for LIC or cloning site features
    insert_site = None

    for feature in record.features:
        label = feature.qualifiers.get('label', [''])[0].lower()

        # Look for LIC site markers
        if 'lic' in label and ('for' in label or 'fwd' in label or 'f' == label[-1]):
            # Forward LIC site - insert goes after this
            insert_site = int(feature.location.end)
            break
        elif 'insert' in label or 'cloning' in label:
            insert_site = int(feature.location.start)
            break

    # If no insertion site found, look for common patterns in sequence
    if insert_site is None:
        # Look for LIC sequence pattern
        lic_pattern = "TACTTCCAATCCAAT"
        pos = sequence.find(lic_pattern)
        if pos != -1:
            insert_site = pos + len(lic_pattern)

    if insert_site is None:
        raise ValueError(f"Could not determine insertion site for vector {name}. "
                        "Please specify --insert-site manually.")

    return {
        'name': name,
        'sequence': sequence,
        'insert_site': insert_site,
        'upstream_seq': sequence[:insert_site],
        'downstream_seq': sequence[insert_site:],
        'length': len(sequence),
    }


def list_available_vectors() -> list:
    """List all available vectors in the vectors directory."""
    vectors = []
    if os.path.isdir(VECTORS_DIR):
        for f in os.listdir(VECTORS_DIR):
            if f.endswith('.gb') or f.endswith('.gbk'):
                name = os.path.splitext(f)[0]
                vectors.append(name)
    return sorted(vectors)


def get_lic_tag(tag_version: str = None, vector: str = None) -> dict:
    """
    Get LIC tag sequences for a given version or vector.

    Args:
        tag_version: Explicit tag version (v1, v2, v3, vKoz, vBac, vGFP1, vGFP2, vHRV)
        vector: Vector name to look up tag version

    Returns:
        Dict with forward, reverse sequences and ORF requirements
    """
    if tag_version:
        if tag_version not in LIC_TAGS:
            raise ValueError(f"Unknown LIC tag version: {tag_version}. "
                           f"Available: {', '.join(LIC_TAGS.keys())}")
        return LIC_TAGS[tag_version]

    if vector:
        # Normalize vector name
        vector_norm = vector.upper().replace("_", "-")
        for v_name, tag in VECTOR_LIC_MAPPING.items():
            if v_name.upper() == vector_norm:
                return LIC_TAGS[tag]
        # Default to v1 if vector not found
        print(f"# Warning: Vector '{vector}' not in mapping, using v1 tags", file=sys.stderr)
        return LIC_TAGS["v1"]

    # Default to v1
    return LIC_TAGS["v1"]


def list_lic_tags() -> str:
    """Return formatted list of available LIC tags."""
    lines = ["Available LIC tag versions:"]
    for tag, info in LIC_TAGS.items():
        atg = "ORF needs ATG" if info["orf_needs_atg"] else "no ATG in ORF"
        lines.append(f"  {tag:6s} F: {info['forward']}")
        lines.append(f"         R: {info['reverse']}")
        lines.append(f"         {atg} | {info['description']}")
    return "\n".join(lines)


class PrimerDesigner:
    """Primer designer for LIC cloning, sequencing, and Gibson assembly."""

    def __init__(self, gene_name: str, sequence: str, index: int = 1,
                 lic_tag: str = "v1", vector: str = None):
        self.gene_name = gene_name
        self.sequence = sequence.upper().replace(" ", "").replace("\n", "")
        self.index = index
        self.lic_tag_version = lic_tag
        self.lic_tag = get_lic_tag(tag_version=lic_tag, vector=vector)
        self.results = {
            "gene_name": gene_name,
            "sequence_length": len(self.sequence),
            "lic_tag_version": lic_tag,
            "lic_tag_description": self.lic_tag["description"],
            "orf_needs_atg": self.lic_tag["orf_needs_atg"],
            "restriction_sites": {},
            "lic_primers": [],
            "sequencing_primers": [],
            "gibson_primers": [],
        }

    def check_restriction_sites(self) -> dict:
        """Check for internal SwaI and PmeI restriction sites."""
        seq = Seq(self.sequence)
        swai_sites = SwaI.search(seq)
        pmei_sites = PmeI.search(seq)

        self.results["restriction_sites"] = {
            "SwaI": swai_sites if swai_sites else [],
            "PmeI": pmei_sites if pmei_sites else [],
        }
        return self.results["restriction_sites"]

    def design_lic_primers(self) -> list:
        """Design LIC cloning primers using the configured LIC tag version."""
        seq_dict = {'SEQUENCE_ID': self.gene_name, 'SEQUENCE_TEMPLATE': self.sequence}
        primers = primer3.design_primers(seq_dict, global_arg_dictionary_lic)

        lic_primers = []
        current_index = self.index

        # Get tag sequences
        fwd_overhang = self.lic_tag["forward"]
        rev_overhang = self.lic_tag["reverse"]
        tag_version = self.lic_tag_version

        # Check if ORF needs ATG and warn if sequence doesn't start with ATG
        if self.lic_tag["orf_needs_atg"] and not self.sequence.startswith("ATG"):
            print(f"# WARNING: {tag_version} requires ORF to start with ATG, "
                  f"but sequence starts with {self.sequence[:3]}", file=sys.stderr)

        # Extract left primer
        for key, value in primers.items():
            if re.match(r"PRIMER_LEFT_0_SEQUENCE", key):
                primer_seq = value
                full_seq = fwd_overhang + primer_seq
                tm = primers.get("PRIMER_LEFT_0_TM", 0)
                lic_primers.append({
                    "index": current_index,
                    "name": f"{initials}{current_index}_{self.gene_name}_LIC{tag_version}_F",
                    "sequence": full_seq,
                    "binding_sequence": primer_seq,
                    "overhang": fwd_overhang,
                    "tm": round(tm, 1),
                    "type": "forward",
                    "tag_version": tag_version,
                })
                current_index += 1
                break

        # Extract right primer
        for key, value in primers.items():
            if re.match(r"PRIMER_RIGHT_0_SEQUENCE", key):
                primer_seq = value
                full_seq = rev_overhang + primer_seq
                tm = primers.get("PRIMER_RIGHT_0_TM", 0)
                lic_primers.append({
                    "index": current_index,
                    "name": f"{initials}{current_index}_{self.gene_name}_LIC{tag_version}_R",
                    "sequence": full_seq,
                    "binding_sequence": primer_seq,
                    "overhang": rev_overhang,
                    "tm": round(tm, 1),
                    "type": "reverse",
                    "tag_version": tag_version,
                })
                current_index += 1
                break

        self.results["lic_primers"] = lic_primers
        self.index = current_index
        return lic_primers

    def design_sequencing_primers(self) -> list:
        """Design sequencing primers spaced ~750bp apart."""
        seq_dict = {'SEQUENCE_ID': self.gene_name, 'SEQUENCE_TEMPLATE': self.sequence}
        primers = primer3.design_primers(seq_dict, global_arg_dictionary_sequencing)

        sequencing_primers = []
        current_index = self.index
        seq_number = 1

        # First primer is reverse (at the start for sequencing from promoter)
        for key, value in primers.items():
            if re.match(r"PRIMER_RIGHT_0_SEQUENCE", key):
                tm = primers.get("PRIMER_RIGHT_0_TM", 0)
                sequencing_primers.append({
                    "index": current_index,
                    "name": f"{initials}{current_index}_{self.gene_name}_Sequencing{seq_number}_R",
                    "sequence": value,
                    "tm": round(tm, 1),
                    "type": "reverse",
                })
                current_index += 1
                seq_number += 1
                break

        # Remaining primers are forward
        left_primers = []
        for key, value in primers.items():
            match = re.match(r"PRIMER_LEFT_(\d+)_SEQUENCE", key)
            if match:
                idx = int(match.group(1))
                left_primers.append((idx, value))

        for idx, value in sorted(left_primers, key=lambda item: item[0]):
            tm = primers.get(f"PRIMER_LEFT_{idx}_TM", 0)
            sequencing_primers.append({
                "index": current_index,
                "name": f"{initials}{current_index}_{self.gene_name}_Sequencing{seq_number}_F",
                "sequence": value,
                "tm": round(tm, 1),
                "type": "forward",
            })
            current_index += 1
            seq_number += 1

        self.results["sequencing_primers"] = sequencing_primers
        self.index = current_index
        return sequencing_primers

    def design_gibson_primers_legacy(self) -> list:
        """Design Gibson assembly primers for sequences >5000bp (legacy fragmentation mode)."""
        if len(self.sequence) <= 5000:
            return []

        gene_length = len(self.sequence)
        estimated_fragments = round(gene_length / 3500)
        estimated_length = round(gene_length / estimated_fragments) + 50

        # Create fragments
        truncated = self.sequence[:-estimated_length]
        fragments = textwrap.wrap(truncated, estimated_length)

        gibson_primers = []
        current_index = self.index
        fragment_num = 1

        for fragment in fragments:
            seq_dict = {'SEQUENCE_ID': f"{self.gene_name}_frag{fragment_num}", 'SEQUENCE_TEMPLATE': fragment}
            primers = primer3.design_primers(seq_dict, global_arg_dictionary_gibson)

            fwd_seq = primers.get("PRIMER_LEFT_0_SEQUENCE")
            rev_seq = primers.get("PRIMER_RIGHT_0_SEQUENCE")
            if fwd_seq and rev_seq:
                fwd_tm = primers.get("PRIMER_LEFT_0_TM", 0)
                rev_tm = primers.get("PRIMER_RIGHT_0_TM", 0)
                gibson_primers.append({
                    "index": current_index,
                    "name": f"{initials}{current_index}_{self.gene_name}_Gibson_Fragment{fragment_num}F",
                    "sequence": fwd_seq,
                    "tm": round(fwd_tm, 1),
                    "type": "forward",
                    "fragment": fragment_num,
                })
                current_index += 1

                gibson_primers.append({
                    "index": current_index,
                    "name": f"{initials}{current_index}_{self.gene_name}_Gibson_Fragment{fragment_num}R",
                    "sequence": rev_seq,
                    "tm": round(rev_tm, 1),
                    "type": "reverse",
                    "fragment": fragment_num,
                })
                current_index += 1

            fragment_num += 1

        self.results["gibson_primers"] = gibson_primers
        self.index = current_index
        return gibson_primers

    def design_hifi_primers(self, vector: dict, target_overlap_tm: float = 60.0) -> list:
        """
        Design Gibson/HiFi assembly primers for cloning insert into vector.

        Creates primers with:
        - 5' overlap tail matching vector sequence (for assembly)
        - 3' gene-specific binding region (for PCR)

        Args:
            vector: Dict from load_vector() with vector info
            target_overlap_tm: Target Tm for overlap regions (default 60°C)

        Returns:
            List of primer dicts
        """
        hifi_primers = []
        current_index = self.index

        # Get vector sequences flanking the insert site
        # Forward primer needs overlap with END of upstream sequence
        # Reverse primer needs overlap with START of downstream sequence
        upstream_seq = vector['upstream_seq']
        downstream_seq = vector['downstream_seq']

        # --- Forward Primer ---
        # Overlap: end of vector upstream sequence
        # Binding: start of insert

        # Find overlap at end of upstream vector sequence
        if len(upstream_seq) < 15:
            raise ValueError("Vector upstream flank is shorter than 15 bp; cannot design HiFi overlap.")
        fwd_overlap, fwd_overlap_tm, fwd_overlap_len = find_overlap_for_tm(
            upstream_seq,
            len(upstream_seq),  # Start from end
            'reverse',          # Extend leftward
            target_overlap_tm
        )
        if not fwd_overlap:
            raise ValueError("Failed to find a suitable upstream overlap for HiFi primers.")

        # Design binding region for start of insert
        seq_dict = {'SEQUENCE_ID': self.gene_name, 'SEQUENCE_TEMPLATE': self.sequence}
        fwd_args = global_arg_dictionary_lic.copy()
        fwd_args['PRIMER_PICK_RIGHT_PRIMER'] = 0
        fwd_primers = primer3.design_primers(seq_dict, fwd_args)

        fwd_binding = None
        fwd_binding_tm = 0
        for key, value in fwd_primers.items():
            if re.match(r"PRIMER_LEFT_0_SEQUENCE", key):
                fwd_binding = value
                fwd_binding_tm = fwd_primers.get("PRIMER_LEFT_0_TM", 0)
                break

        if fwd_binding:
            full_fwd = fwd_overlap + fwd_binding
            hifi_primers.append({
                "index": current_index,
                "name": f"{initials}{current_index}_{self.gene_name}_HiFi_F",
                "sequence": full_fwd,
                "binding_sequence": fwd_binding,
                "binding_tm": round(fwd_binding_tm, 1),
                "overlap_sequence": fwd_overlap,
                "overlap_tm": round(fwd_overlap_tm, 1),
                "overlap_length": fwd_overlap_len,
                "type": "forward",
                "vector": vector['name'],
            })
            current_index += 1

        # --- Reverse Primer ---
        # Overlap: start of vector downstream sequence (reverse complement)
        # Binding: end of insert (reverse complement)

        # Find overlap at start of downstream vector sequence
        if len(downstream_seq) < 15:
            raise ValueError("Vector downstream flank is shorter than 15 bp; cannot design HiFi overlap.")
        rev_overlap, rev_overlap_tm, rev_overlap_len = find_overlap_for_tm(
            downstream_seq,
            0,          # Start from beginning
            'forward',  # Extend rightward
            target_overlap_tm
        )
        if not rev_overlap:
            raise ValueError("Failed to find a suitable downstream overlap for HiFi primers.")
        # Reverse complement the overlap for the primer
        rev_overlap_rc = str(Seq(rev_overlap).reverse_complement())

        # Design binding region for end of insert
        rev_args = global_arg_dictionary_lic.copy()
        rev_args['PRIMER_PICK_LEFT_PRIMER'] = 0
        rev_primers = primer3.design_primers(seq_dict, rev_args)

        rev_binding = None
        rev_binding_tm = 0
        for key, value in rev_primers.items():
            if re.match(r"PRIMER_RIGHT_0_SEQUENCE", key):
                rev_binding = value
                rev_binding_tm = rev_primers.get("PRIMER_RIGHT_0_TM", 0)
                break

        if rev_binding:
            full_rev = rev_overlap_rc + rev_binding
            hifi_primers.append({
                "index": current_index,
                "name": f"{initials}{current_index}_{self.gene_name}_HiFi_R",
                "sequence": full_rev,
                "binding_sequence": rev_binding,
                "binding_tm": round(rev_binding_tm, 1),
                "overlap_sequence": rev_overlap_rc,
                "overlap_tm": round(rev_overlap_tm, 1),
                "overlap_length": rev_overlap_len,
                "type": "reverse",
                "vector": vector['name'],
            })
            current_index += 1

        self.results["hifi_primers"] = hifi_primers
        self.results["vector"] = vector['name']
        self.results["target_overlap_tm"] = target_overlap_tm
        self.index = current_index
        return hifi_primers


def fetch_ncbi_sequence(accession: str) -> tuple:
    """Fetch gene sequence from NCBI by accession number."""
    Entrez.email = email_address

    try:
        handle = Entrez.efetch(db='nucleotide', id=accession, rettype='gb', retmode='text')
        gene_name = None
        gene_sequence = None

        for rec in SeqIO.parse(handle, "genbank"):
            if rec.features:
                for feature in rec.features:
                    if feature.type == "CDS":
                        if "gene" in feature.qualifiers:
                            gene_name = feature.qualifiers["gene"][0]
                        elif "product" in feature.qualifiers:
                            gene_name = feature.qualifiers["product"][0].replace(" ", "_")[:20]
                        gene_sequence = str(feature.location.extract(rec).seq)
                        break

        if gene_sequence is None:
            # Fall back to full sequence if no CDS found
            handle = Entrez.efetch(db='nucleotide', id=accession, rettype='fasta', retmode='text')
            for rec in SeqIO.parse(handle, "fasta"):
                gene_sequence = str(rec.seq)
                gene_name = gene_name or accession.replace(".", "_")
                break

        handle.close()

        if gene_sequence is None:
            raise ValueError(f"Could not extract sequence from accession {accession}")

        return gene_name or accession, gene_sequence

    except Exception as e:
        raise ValueError(f"Failed to fetch NCBI accession {accession}: {e}")


def format_output(results: dict, json_output: bool) -> str:
    """Format results for output."""
    if json_output:
        return json.dumps(results, indent=2)

    lines = []
    lines.append(f"# Primer Design Results for {results['gene_name']}")
    lines.append(f"# Sequence length: {results['sequence_length']} bp")

    if results.get("lic_tag_version"):
        lines.append(f"# LIC tag: {results['lic_tag_version']} - {results.get('lic_tag_description', '')}")
        if results.get("orf_needs_atg"):
            lines.append(f"# NOTE: ORF must start with ATG for this tag version")

    if results.get("vector"):
        lines.append(f"# Vector: {results['vector']}")
    if results.get("target_overlap_tm"):
        lines.append(f"# Target overlap Tm: {results['target_overlap_tm']}°C")

    lines.append("")

    # Restriction sites
    rs = results.get("restriction_sites", {})
    if rs.get("SwaI"):
        lines.append(f"# WARNING: Internal SwaI site(s) found at: {rs['SwaI']}")
    else:
        lines.append("# No internal SwaI site")
    if rs.get("PmeI"):
        lines.append(f"# WARNING: Internal PmeI site(s) found at: {rs['PmeI']}")
    else:
        lines.append("# No internal PmeI site")
    lines.append("")

    # HiFi/Gibson primers (new format)
    if results.get("hifi_primers"):
        lines.append("# HiFi/Gibson Assembly Primers")
        lines.append("# Format: [overlap tail for assembly] + [gene-specific binding region]")
        lines.append("")
        for p in results["hifi_primers"]:
            lines.append(f"{p['name']}\t{p['sequence']}")
            lines.append(f"  # Overlap: {p['overlap_sequence']} (Tm: {p['overlap_tm']}°C, {p['overlap_length']} bp)")
            lines.append(f"  # Binding: {p['binding_sequence']} (Tm: {p['binding_tm']}°C)")
        lines.append("")

    # LIC primers
    if results.get("lic_primers"):
        lines.append("# LIC Cloning Primers")
        for p in results["lic_primers"]:
            lines.append(f"{p['name']}\t{p['sequence']}")
        lines.append("")

    # Gibson primers (legacy)
    if results.get("gibson_primers"):
        lines.append("# Gibson Assembly Primers (fragmentation)")
        for p in results["gibson_primers"]:
            lines.append(f"{p['name']}\t{p['sequence']}")
        lines.append("")

    # Sequencing primers
    if results.get("sequencing_primers"):
        lines.append("# Sequencing Primers")
        for p in results["sequencing_primers"]:
            lines.append(f"{p['name']}\t{p['sequence']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Design PCR primers for LIC cloning, sequencing, and Gibson/HiFi assembly.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # LIC cloning primers (default v1 tags for N-terminal fusions)
  %(prog)s --index 1 --accession NM_001234567
  %(prog)s --index 1 --sequence ATGCATGC... --gene MyGene

  # Specify LIC tag version explicitly
  %(prog)s --index 1 --accession NM_001234567 --lic-tag v2    # Untagged (needs ATG)
  %(prog)s --index 1 --accession NM_001234567 --lic-tag v3    # C-terminal tags
  %(prog)s --index 1 --accession NM_001234567 --lic-tag vBac  # Baculovirus

  # LIC tag is auto-selected when using --vector
  %(prog)s --index 1 --accession NM_001234567 --vector 438-B  # auto: v1
  %(prog)s --index 1 --accession NM_001234567 --vector 2AT    # auto: v2

  # Gibson/HiFi assembly primers
  %(prog)s --index 1 --accession NM_007192 --hifi --vector 438-A
  %(prog)s --index 1 --accession NM_007192 --hifi --vector 438-B --overlap-tm 65

  # List available options
  %(prog)s --list-lic-tags
  %(prog)s --list-vectors

  # Sequencing primers only
  %(prog)s --index 1 --accession NM_001234567 --seq-only
        """
    )

    parser.add_argument('--index', '-i', type=int,
                        help='Starting index number for primer naming')
    parser.add_argument('--accession', '-a', metavar='ID',
                        help='NCBI accession code (NM_ or XM_ prefix)')
    parser.add_argument('--sequence', '-s', metavar='SEQUENCE',
                        help='Raw DNA sequence (ATCG only)')
    parser.add_argument('--gene', '-g', metavar='NAME',
                        help='Gene name (required with --sequence)')

    # LIC tag options
    parser.add_argument('--lic-tag', '-t', metavar='VERSION', default='v1',
                        help='LIC tag version: v1 (default), v2, v3, vKoz, vBac, vGFP1, vGFP2, vHRV')
    parser.add_argument('--list-lic-tags', action='store_true',
                        help='List available LIC tag versions and exit')

    # HiFi/Gibson assembly options
    parser.add_argument('--hifi', '--gibson', action='store_true',
                        help='Design HiFi/Gibson assembly primers (requires --vector)')
    parser.add_argument('--vector', '-v', metavar='NAME',
                        help='Vector name (e.g., 438-A) or path to GenBank file. '
                             'Also auto-selects appropriate LIC tag version.')
    parser.add_argument('--overlap-tm', type=float, default=60.0,
                        help='Target Tm for overlap regions (default: 60°C)')
    parser.add_argument('--list-vectors', action='store_true',
                        help='List available vectors and exit')

    # Other options
    parser.add_argument('--no-gibson', action='store_true',
                        help='Disable legacy Gibson fragmentation for sequences >5000bp')
    parser.add_argument('--lic-only', action='store_true',
                        help='Only generate LIC cloning primers')
    parser.add_argument('--seq-only', action='store_true',
                        help='Only generate sequencing primers')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')

    args = parser.parse_args()

    # Handle --list-lic-tags
    if args.list_lic_tags:
        print(list_lic_tags())
        return 0

    # Handle --list-vectors
    if args.list_vectors:
        vectors = list_available_vectors()
        if vectors:
            print("Available vectors:")
            for v in vectors:
                print(f"  {v}")
        else:
            print(f"No vectors found in {VECTORS_DIR}")
        return 0

    # Validate arguments
    if not args.accession and not args.sequence:
        parser.error("Either --accession or --sequence is required")

    if args.sequence and not args.gene:
        parser.error("--gene is required when using --sequence")

    if args.lic_only and args.seq_only:
        parser.error("Cannot use both --lic-only and --seq-only")

    if args.hifi and not args.vector:
        parser.error("--vector is required when using --hifi/--gibson")

    if not args.index:
        parser.error("--index is required")

    # Load vector if specified
    vector = None
    if args.vector:
        try:
            vector = load_vector(args.vector)
            print(f"# Loaded vector: {vector['name']} ({vector['length']} bp, insert site: {vector['insert_site']})",
                  file=sys.stderr)
        except Exception as e:
            print(f"Error loading vector: {e}", file=sys.stderr)
            return 1

    # Get sequence
    try:
        if args.accession:
            gene_name, sequence = fetch_ncbi_sequence(args.accession)
        else:
            gene_name = args.gene
            sequence = args.sequence

        # Validate sequence
        sequence = sequence.upper().replace(" ", "").replace("\n", "")
        if not re.match(r'^[ATCG]+$', sequence):
            print("Error: Sequence must contain only A, T, C, G characters", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine LIC tag version
    # Priority: explicit --lic-tag > auto-detect from vector > default v1
    lic_tag = args.lic_tag
    if args.vector and args.lic_tag == 'v1':
        # Auto-detect from vector if user didn't explicitly specify
        vector_name = os.path.splitext(os.path.basename(args.vector))[0] if os.path.isfile(args.vector) else args.vector
        for v_name, tag in VECTOR_LIC_MAPPING.items():
            if v_name.upper().replace("_", "-") == vector_name.upper().replace("_", "-"):
                lic_tag = tag
                print(f"# Auto-selected LIC tag {lic_tag} for vector {vector_name}", file=sys.stderr)
                break

    # Design primers
    designer = PrimerDesigner(gene_name, sequence, args.index, lic_tag=lic_tag)

    # Check restriction sites
    designer.check_restriction_sites()

    # Design primers based on options
    if args.hifi:
        # HiFi/Gibson assembly mode
        designer.design_hifi_primers(vector, args.overlap_tm)
    elif args.seq_only:
        designer.design_sequencing_primers()
    elif args.lic_only:
        designer.design_lic_primers()
    else:
        designer.design_lic_primers()
        if len(sequence) > 5000 and not args.no_gibson:
            designer.design_gibson_primers_legacy()
        designer.design_sequencing_primers()

    # Output results
    output = format_output(designer.results, args.json)
    print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
