#!/usr/bin/env python3
"""
Reactor CLI - Buffer Calculator

Calculate reaction buffer recipes accounting for buffer components contributed
by protein stocks. Supports direct calculation and compensation buffer modes.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Try to import YAML, fall back to JSON-only if not available
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# =============================================================================
# Type Definitions
# =============================================================================

ConcentrationUnit = str  # 'M', 'mM', 'uM', 'nM', 'pmol', '%', 'mg/ml'


@dataclass
class BufferComponent:
    """A buffer component with stock and final concentrations."""
    name: str
    stock_concentration: float
    stock_unit: ConcentrationUnit
    final_concentration: Optional[float] = None
    final_unit: Optional[ConcentrationUnit] = None


@dataclass
class Protein:
    """A protein with concentration, stock info, and buffer components."""
    name: str
    amount: float
    unit: ConcentrationUnit
    stock_concentration: float
    stock_unit: ConcentrationUnit
    buffer_components: List[BufferComponent] = field(default_factory=list)


@dataclass
class RecipeEntry:
    """An entry in the calculated recipe."""
    volume: float
    stock_concentration: Optional[float] = None
    stock_unit: Optional[str] = None
    final_concentration: Optional[float] = None
    final_unit: Optional[str] = None


@dataclass
class DirectRecipeResult:
    """Result of a direct buffer calculation."""
    recipe: Dict[str, RecipeEntry]
    protein_volumes: Dict[str, float]
    warnings: List[str]
    total_calculated_volume: float
    buffer_contributions: Dict[str, float]


@dataclass
class CompensationRecipeResult:
    """Result of a compensation buffer calculation."""
    compensation_buffer: Dict[str, RecipeEntry]
    compensation_buffer_1ml: Dict[str, RecipeEntry]
    protein_volumes: Dict[str, float]
    buffer_volume_needed: float
    total_reaction_volume: float
    warnings: List[str]
    compensation_fold: int


# =============================================================================
# Predefined Stocks
# =============================================================================

PREDEFINED_STOCKS: Dict[str, Tuple[float, ConcentrationUnit]] = {
    'HEPES': (1.0, 'M'),
    'NaCl': (5.0, 'M'),
    'KCl': (3.0, 'M'),
    'MgCl2': (1.0, 'M'),
    'CaCl2': (1.0, 'M'),
    'Tris': (1.0, 'M'),
    'TCEP': (500.0, 'mM'),
    'DTT': (1.0, 'M'),
    'EDTA': (500.0, 'mM'),
    'EGTA': (500.0, 'mM'),
    'Glycerol': (100.0, '%'),
    'ATP': (100.0, 'mM'),
    'GTP': (100.0, 'mM'),
    'Imidazole': (2.0, 'M'),
    'BME': (14.3, 'M'),  # Beta-mercaptoethanol
    'Triton': (100.0, '%'),  # Triton X-100
    'NP40': (10.0, '%'),
    'SDS': (10.0, '%'),
    'Urea': (8.0, 'M'),
}


# =============================================================================
# Presets
# =============================================================================

PROTEIN_PRESETS: Dict[str, List[dict]] = {
    'kinase_panel': [
        {
            'name': 'CDK2',
            'amount': 50,
            'unit': 'nM',
            'stock_concentration': 10000,
            'stock_unit': 'nM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 150, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'MEK1',
            'amount': 25,
            'unit': 'nM',
            'stock_concentration': 8000,
            'stock_unit': 'nM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 150, 'stock_unit': 'mM'},
                {'name': 'DTT', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
    ],
    'purification_stocks': [
        {
            'name': 'His-tagged protein',
            'amount': 30,
            'unit': 'uM',
            'stock_concentration': 1500,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'Imidazole', 'stock_concentration': 300, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 300, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'TEV protease',
            'amount': 5,
            'unit': 'uM',
            'stock_concentration': 100,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'Glycerol', 'stock_concentration': 50, 'stock_unit': '%'},
                {'name': 'DTT', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
    ],
    'reconstitution': [
        {
            'name': 'Histone octamer',
            'amount': 10,
            'unit': 'uM',
            'stock_concentration': 100,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'NaCl', 'stock_concentration': 2000, 'stock_unit': 'mM'},
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'DNA',
            'amount': 8,
            'unit': 'uM',
            'stock_concentration': 50,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'Tris', 'stock_concentration': 10, 'stock_unit': 'mM'},
                {'name': 'EDTA', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
    ],
    'polii_elongation_complex': [
        {
            'name': 'PolII',
            'amount': 700,
            'unit': 'nM',
            'stock_concentration': 5.17,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 150, 'stock_unit': 'mM'},
                {'name': 'Glycerol', 'stock_concentration': 10, 'stock_unit': '%'},
                {'name': 'TCEP', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'DSIF',
            'amount': 1050,
            'unit': 'nM',
            'stock_concentration': 50.8,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 500, 'stock_unit': 'mM'},
                {'name': 'Glycerol', 'stock_concentration': 10, 'stock_unit': '%'},
                {'name': 'TCEP', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'IWS1',
            'amount': 1050,
            'unit': 'nM',
            'stock_concentration': 84.1,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 300, 'stock_unit': 'mM'},
                {'name': 'Glycerol', 'stock_concentration': 10, 'stock_unit': '%'},
                {'name': 'TCEP', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'ELOF1',
            'amount': 1050,
            'unit': 'nM',
            'stock_concentration': 104.5,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 300, 'stock_unit': 'mM'},
                {'name': 'Glycerol', 'stock_concentration': 10, 'stock_unit': '%'},
                {'name': 'TCEP', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'SPT6',
            'amount': 1050,
            'unit': 'nM',
            'stock_concentration': 77.73,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 300, 'stock_unit': 'mM'},
                {'name': 'Glycerol', 'stock_concentration': 10, 'stock_unit': '%'},
                {'name': 'TCEP', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'PAF1c',
            'amount': 1050,
            'unit': 'nM',
            'stock_concentration': 29.7,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 300, 'stock_unit': 'mM'},
                {'name': 'Glycerol', 'stock_concentration': 10, 'stock_unit': '%'},
                {'name': 'TCEP', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'P-TEFb',
            'amount': 1050,
            'unit': 'nM',
            'stock_concentration': 36.4,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 300, 'stock_unit': 'mM'},
                {'name': 'Glycerol', 'stock_concentration': 10, 'stock_unit': '%'},
                {'name': 'TCEP', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'CSB',
            'amount': 1050,
            'unit': 'nM',
            'stock_concentration': 56.9,
            'stock_unit': 'uM',
            'buffer_components': [
                {'name': 'HEPES', 'stock_concentration': 20, 'stock_unit': 'mM'},
                {'name': 'NaCl', 'stock_concentration': 500, 'stock_unit': 'mM'},
                {'name': 'Glycerol', 'stock_concentration': 10, 'stock_unit': '%'},
                {'name': 'TCEP', 'stock_concentration': 1, 'stock_unit': 'mM'},
            ],
        },
        {
            'name': 'DNA-RNA',
            'amount': 840,
            'unit': 'nM',
            'stock_concentration': 50,
            'stock_unit': 'uM',
            'buffer_components': [],
        },
        {
            'name': 'ntDNA',
            'amount': 1400,
            'unit': 'nM',
            'stock_concentration': 100,
            'stock_unit': 'uM',
            'buffer_components': [],
        },
    ],
}

BUFFER_PRESETS: Dict[str, List[dict]] = {
    'lysis': [
        {'name': 'HEPES', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 50, 'final_unit': 'mM'},
        {'name': 'NaCl', 'stock_concentration': 5, 'stock_unit': 'M', 'final_concentration': 300, 'final_unit': 'mM'},
        {'name': 'TCEP', 'stock_concentration': 500, 'stock_unit': 'mM', 'final_concentration': 1, 'final_unit': 'mM'},
        {'name': 'Glycerol', 'stock_concentration': 100, 'stock_unit': '%', 'final_concentration': 5, 'final_unit': '%'},
    ],
    'gel_filtration': [
        {'name': 'Tris', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 25, 'final_unit': 'mM'},
        {'name': 'NaCl', 'stock_concentration': 5, 'stock_unit': 'M', 'final_concentration': 150, 'final_unit': 'mM'},
        {'name': 'EDTA', 'stock_concentration': 500, 'stock_unit': 'mM', 'final_concentration': 1, 'final_unit': 'mM'},
        {'name': 'Glycerol', 'stock_concentration': 100, 'stock_unit': '%', 'final_concentration': 10, 'final_unit': '%'},
    ],
    'storage': [
        {'name': 'HEPES', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 20, 'final_unit': 'mM'},
        {'name': 'NaCl', 'stock_concentration': 5, 'stock_unit': 'M', 'final_concentration': 150, 'final_unit': 'mM'},
        {'name': 'TCEP', 'stock_concentration': 500, 'stock_unit': 'mM', 'final_concentration': 0.5, 'final_unit': 'mM'},
        {'name': 'Glycerol', 'stock_concentration': 100, 'stock_unit': '%', 'final_concentration': 10, 'final_unit': '%'},
    ],
    'kinase_assay': [
        {'name': 'HEPES', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 25, 'final_unit': 'mM'},
        {'name': 'NaCl', 'stock_concentration': 5, 'stock_unit': 'M', 'final_concentration': 100, 'final_unit': 'mM'},
        {'name': 'MgCl2', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 10, 'final_unit': 'mM'},
        {'name': 'DTT', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 1, 'final_unit': 'mM'},
        {'name': 'ATP', 'stock_concentration': 100, 'stock_unit': 'mM', 'final_concentration': 1, 'final_unit': 'mM'},
    ],
    'cryo_em': [
        {'name': 'HEPES', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 20, 'final_unit': 'mM'},
        {'name': 'NaCl', 'stock_concentration': 5, 'stock_unit': 'M', 'final_concentration': 100, 'final_unit': 'mM'},
        {'name': 'Glycerol', 'stock_concentration': 100, 'stock_unit': '%', 'final_concentration': 10, 'final_unit': 'mM'},
        {'name': 'TCEP', 'stock_concentration': 500, 'stock_unit': 'mM', 'final_concentration': 1, 'final_unit': 'mM'},
    ],
    'elongation_buffer': [
        {'name': 'HEPES', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 20, 'final_unit': 'mM'},
        {'name': 'NaCl', 'stock_concentration': 5, 'stock_unit': 'M', 'final_concentration': 75, 'final_unit': 'mM'},
        {'name': 'Glycerol', 'stock_concentration': 100, 'stock_unit': '%', 'final_concentration': 10, 'final_unit': '%'},
        {'name': 'TCEP', 'stock_concentration': 200, 'stock_unit': 'mM', 'final_concentration': 1, 'final_unit': 'mM'},
        {'name': 'ATP', 'stock_concentration': 100, 'stock_unit': 'mM', 'final_concentration': 1, 'final_unit': 'mM'},
        {'name': 'MgCl2', 'stock_concentration': 1, 'stock_unit': 'M', 'final_concentration': 3, 'final_unit': 'mM'},
    ],
}


# =============================================================================
# External Preset Loading
# =============================================================================

# Default preset file locations (searched in order)
PRESET_FILE_LOCATIONS = [
    Path.home() / '.config' / 'reactor' / 'presets.yaml',
    Path.home() / '.config' / 'reactor' / 'presets.json',
]

# Merged presets (built-in + external)
MERGED_PROTEIN_PRESETS: Dict[str, List[dict]] = {}
MERGED_BUFFER_PRESETS: Dict[str, List[dict]] = {}


def load_external_presets(preset_file: Optional[Path] = None) -> Tuple[Dict, Dict]:
    """
    Load presets from external YAML/JSON file.

    Returns tuple of (protein_presets, buffer_presets).
    """
    protein_presets = {}
    buffer_presets = {}

    # Find preset file
    if preset_file:
        files_to_try = [Path(preset_file)]
    else:
        files_to_try = PRESET_FILE_LOCATIONS

    loaded_file = None
    for f in files_to_try:
        if f.exists():
            loaded_file = f
            break

    if not loaded_file:
        return protein_presets, buffer_presets

    try:
        with open(loaded_file, 'r') as fp:
            if loaded_file.suffix in ('.yaml', '.yml'):
                if not YAML_AVAILABLE:
                    print(f"Warning: PyYAML not installed, cannot load {loaded_file}",
                          file=sys.stderr)
                    return protein_presets, buffer_presets
                data = yaml.safe_load(fp)
            else:
                data = json.load(fp)

        if not isinstance(data, dict):
            print(f"Warning: Invalid preset file format in {loaded_file}", file=sys.stderr)
            return protein_presets, buffer_presets

        # Load protein presets (preserve full structure for reference_amount support)
        if 'protein_presets' in data:
            for name, preset in data['protein_presets'].items():
                # Keep the full preset dict to preserve reference_amount, reference_unit, etc.
                protein_presets[name] = preset

        # Load buffer presets (preserve full structure)
        if 'buffer_presets' in data:
            for name, preset in data['buffer_presets'].items():
                # Keep the full preset dict
                buffer_presets[name] = preset

        # Print info about loaded file
        n_proteins = len(protein_presets)
        n_buffers = len(buffer_presets)
        if n_proteins > 0 or n_buffers > 0:
            print(f"Loaded {n_proteins} protein and {n_buffers} buffer presets from {loaded_file}",
                  file=sys.stderr)

    except Exception as e:
        print(f"Warning: Error loading preset file {loaded_file}: {e}", file=sys.stderr)

    return protein_presets, buffer_presets


def init_merged_presets(preset_file: Optional[Path] = None):
    """Initialize merged presets from built-in and external sources."""
    global MERGED_PROTEIN_PRESETS, MERGED_BUFFER_PRESETS

    # Start with built-in presets
    MERGED_PROTEIN_PRESETS = dict(PROTEIN_PRESETS)
    MERGED_BUFFER_PRESETS = dict(BUFFER_PRESETS)

    # Load and merge external presets (external overrides built-in)
    ext_proteins, ext_buffers = load_external_presets(preset_file)
    MERGED_PROTEIN_PRESETS.update(ext_proteins)
    MERGED_BUFFER_PRESETS.update(ext_buffers)


# =============================================================================
# Buffer Calculator
# =============================================================================

class BufferCalculator:
    """Calculate buffer recipes accounting for protein stock contributions."""

    def __init__(self):
        self.predefined_stocks = PREDEFINED_STOCKS

    def normalize_unit(self, unit: str) -> str:
        """Normalize unit strings."""
        unit = unit.strip()
        # Handle common variations
        if unit.lower() in ('um', 'μm', 'µm'):
            return 'uM'
        if unit.lower() == 'nm':
            return 'nM'
        if unit.lower() == 'mm':
            return 'mM'
        if unit.lower() == 'm':
            return 'M'
        return unit

    def is_percentage_unit(self, unit: str) -> bool:
        """Check if unit is a percentage or non-molar unit."""
        unit = self.normalize_unit(unit)
        return unit in ('%', 'mg/ml')

    def convert_to_mm(self, value: float, unit: str) -> float:
        """Convert concentration to millimolar."""
        unit = self.normalize_unit(unit)
        if unit == 'M':
            return value * 1000.0
        elif unit == 'mM':
            return value
        elif unit == 'uM':
            return value / 1000.0
        elif unit == 'nM':
            return value / 1_000_000.0
        elif unit == '%':
            return value  # Keep as-is for percentage (special handling needed)
        elif unit == 'mg/ml':
            return value  # Keep as-is
        else:
            raise ValueError(f"Unsupported unit: {unit}")

    def convert_concentration(self, value: float, from_unit: str, to_unit: str) -> float:
        """Convert concentration between units."""
        from_unit = self.normalize_unit(from_unit)
        to_unit = self.normalize_unit(to_unit)

        if from_unit == to_unit:
            return value

        # Handle percentage separately
        if from_unit == '%' or to_unit == '%':
            if from_unit == '%' and to_unit == '%':
                return value
            raise ValueError(f"Cannot convert between % and {to_unit if from_unit == '%' else from_unit}")

        # Convert to mM as base
        mm_value = self.convert_to_mm(value, from_unit)

        # Convert from mM to target
        if to_unit == 'M':
            return mm_value / 1000.0
        elif to_unit == 'mM':
            return mm_value
        elif to_unit == 'uM':
            return mm_value * 1000.0
        elif to_unit == 'nM':
            return mm_value * 1_000_000.0
        else:
            raise ValueError(f"Unsupported target unit: {to_unit}")

    def calculate_protein_volume(self, protein: Protein, total_volume: float) -> float:
        """Calculate volume of protein stock needed."""
        if protein.amount <= 0:
            return 0.0
        if protein.stock_concentration <= 0:
            raise ValueError(f"Invalid stock concentration for {protein.name}")
        if total_volume <= 0:
            raise ValueError("Invalid total volume")

        # Convert both to the same unit (uM)
        final_conc = self.convert_concentration(protein.amount, protein.unit, 'uM')
        stock_conc = self.convert_concentration(protein.stock_concentration, protein.stock_unit, 'uM')

        if stock_conc <= 0:
            raise ValueError(f"Invalid stock concentration for {protein.name}")

        return (final_conc * total_volume) / stock_conc

    def calculate_buffer_contribution(
        self, proteins: List[Protein], total_volume: float
    ) -> Dict[str, Tuple[float, str]]:
        """
        Calculate buffer component contributions from protein stocks.

        Returns dict of component name -> (contribution_value, unit)
        """
        contributions: Dict[str, Tuple[float, str]] = {}

        for protein in proteins:
            if protein.amount <= 0:
                continue

            try:
                protein_volume = self.calculate_protein_volume(protein, total_volume)

                for component in protein.buffer_components:
                    if not component.name or component.stock_concentration <= 0:
                        continue

                    # Keep track of original unit for percentage handling
                    unit = self.normalize_unit(component.stock_unit)
                    stock_conc = component.stock_concentration

                    # Contribution = (stock_conc * protein_volume) / total_volume
                    contribution = (stock_conc * protein_volume) / total_volume

                    if component.name in contributions:
                        prev_val, prev_unit = contributions[component.name]
                        # Only add if same unit type
                        if prev_unit == unit:
                            contributions[component.name] = (prev_val + contribution, unit)
                    else:
                        contributions[component.name] = (contribution, unit)

            except Exception as e:
                print(f"Warning: Error calculating contribution for {protein.name}: {e}",
                      file=sys.stderr)

        return contributions

    def calculate_direct_recipe(
        self,
        proteins: List[Protein],
        buffer_components: List[BufferComponent],
        total_volume: float,
    ) -> DirectRecipeResult:
        """Calculate direct buffer recipe."""
        result = DirectRecipeResult(
            recipe={},
            protein_volumes={},
            warnings=[],
            total_calculated_volume=0,
            buffer_contributions={},
        )

        # Calculate protein volumes
        total_protein_volume = 0.0
        for protein in proteins:
            if protein.amount > 0:
                try:
                    volume = self.calculate_protein_volume(protein, total_volume)
                    result.protein_volumes[protein.name] = volume
                    total_protein_volume += volume
                except Exception as e:
                    result.warnings.append(f"Error calculating {protein.name}: {e}")

        if total_protein_volume > total_volume * 0.5:
            result.warnings.append("Protein volumes exceed 50% of total volume")

        # Calculate buffer contributions from proteins
        buffer_contributions = self.calculate_buffer_contribution(proteins, total_volume)
        # Convert to simple dict for output (value only, for display)
        result.buffer_contributions = {k: v[0] for k, v in buffer_contributions.items()}

        # Calculate buffer component volumes
        buffer_volume = 0.0
        for component in buffer_components:
            if component.final_concentration is None or component.final_concentration <= 0:
                continue

            final_unit = self.normalize_unit(component.final_unit or component.stock_unit)

            # Get protein contribution
            protein_contribution = 0.0
            if component.name in buffer_contributions:
                contrib_val, contrib_unit = buffer_contributions[component.name]
                contrib_unit = self.normalize_unit(contrib_unit)

                # Only use contribution if units are compatible
                if self.is_percentage_unit(final_unit) == self.is_percentage_unit(contrib_unit):
                    if final_unit == contrib_unit:
                        protein_contribution = contrib_val
                    elif not self.is_percentage_unit(final_unit):
                        # Both are molar units, convert
                        protein_contribution = self.convert_concentration(contrib_val, contrib_unit, final_unit)

            needed_concentration = component.final_concentration - protein_contribution

            if needed_concentration <= 0:
                result.warnings.append(
                    f"{component.name}: Protein stocks already provide sufficient concentration"
                )
                continue

            # Convert stock concentration to final unit (only if compatible)
            stock_unit = self.normalize_unit(component.stock_unit)
            if self.is_percentage_unit(final_unit) != self.is_percentage_unit(stock_unit):
                result.warnings.append(
                    f"{component.name}: Incompatible units ({stock_unit} vs {final_unit})"
                )
                continue

            if final_unit == stock_unit:
                stock_conc = component.stock_concentration
            else:
                stock_conc = self.convert_concentration(
                    component.stock_concentration, stock_unit, final_unit
                )

            if stock_conc < needed_concentration:
                result.warnings.append(
                    f"{component.name}: Required ({needed_concentration:.2f} {final_unit}) "
                    f"exceeds stock ({stock_conc:.2f} {final_unit})"
                )
                continue

            volume_needed = (needed_concentration * total_volume) / stock_conc

            result.recipe[component.name] = RecipeEntry(
                volume=volume_needed,
                stock_concentration=component.stock_concentration,
                stock_unit=component.stock_unit,
                final_concentration=component.final_concentration,
                final_unit=final_unit,
            )
            buffer_volume += volume_needed

        # Calculate water volume
        total_calculated = total_protein_volume + buffer_volume
        water_volume = total_volume - total_calculated

        if water_volume < 0:
            result.warnings.append("Calculated volumes exceed total volume")
            water_volume = 0

        result.recipe['Water'] = RecipeEntry(volume=water_volume)
        result.total_calculated_volume = total_calculated + water_volume

        return result

    def calculate_compensation_buffer(
        self,
        proteins: List[Protein],
        buffer_components: List[BufferComponent],
        total_volume: float,
        compensation_fold: int,
    ) -> CompensationRecipeResult:
        """Calculate compensation buffer (concentrated buffer)."""
        buffer_volume_needed = total_volume / compensation_fold

        result = CompensationRecipeResult(
            compensation_buffer={},
            compensation_buffer_1ml={},
            protein_volumes={},
            buffer_volume_needed=buffer_volume_needed,
            total_reaction_volume=total_volume,
            warnings=[],
            compensation_fold=compensation_fold,
        )

        # Calculate protein volumes
        for protein in proteins:
            if protein.amount > 0:
                try:
                    volume = self.calculate_protein_volume(protein, total_volume)
                    result.protein_volumes[protein.name] = volume
                except Exception as e:
                    result.warnings.append(f"Error calculating {protein.name}: {e}")

        # Calculate buffer contributions
        buffer_contributions = self.calculate_buffer_contribution(proteins, total_volume)

        # Calculate compensation buffer components
        total_component_volume = 0.0
        for component in buffer_components:
            if component.final_concentration is None or component.final_concentration <= 0:
                continue

            final_unit = self.normalize_unit(component.final_unit or component.stock_unit)

            # Get protein contribution
            protein_contribution = 0.0
            if component.name in buffer_contributions:
                contrib_val, contrib_unit = buffer_contributions[component.name]
                contrib_unit = self.normalize_unit(contrib_unit)

                # Only use contribution if units are compatible
                if self.is_percentage_unit(final_unit) == self.is_percentage_unit(contrib_unit):
                    if final_unit == contrib_unit:
                        protein_contribution = contrib_val
                    elif not self.is_percentage_unit(final_unit):
                        protein_contribution = self.convert_concentration(contrib_val, contrib_unit, final_unit)

            needed_concentration = component.final_concentration - protein_contribution
            if needed_concentration <= 0:
                continue

            # Compensation buffer needs to be more concentrated
            compensation_concentration = needed_concentration * compensation_fold

            # Convert stock concentration (only if compatible units)
            stock_unit = self.normalize_unit(component.stock_unit)
            if self.is_percentage_unit(final_unit) != self.is_percentage_unit(stock_unit):
                result.warnings.append(
                    f"{component.name}: Incompatible units ({stock_unit} vs {final_unit})"
                )
                continue

            if final_unit == stock_unit:
                stock_conc = component.stock_concentration
            else:
                stock_conc = self.convert_concentration(
                    component.stock_concentration, stock_unit, final_unit
                )

            if stock_conc < compensation_concentration:
                result.warnings.append(
                    f"{component.name}: Required {compensation_fold}X concentration "
                    f"({compensation_concentration:.2f} {final_unit}) exceeds stock "
                    f"({stock_conc:.2f} {final_unit})"
                )
                continue

            volume_needed = (compensation_concentration * buffer_volume_needed) / stock_conc

            result.compensation_buffer[component.name] = RecipeEntry(
                volume=volume_needed,
                stock_concentration=component.stock_concentration,
                stock_unit=component.stock_unit,
                final_concentration=compensation_concentration,
                final_unit=final_unit,
            )
            total_component_volume += volume_needed

        # Add water
        water_volume = buffer_volume_needed - total_component_volume
        if water_volume < 0:
            result.warnings.append("Compensation buffer components exceed buffer volume")
            water_volume = 0

        result.compensation_buffer['Water'] = RecipeEntry(volume=water_volume)

        # Scale to 1 mL
        scale_factor = 1000.0 / buffer_volume_needed
        for name, entry in result.compensation_buffer.items():
            result.compensation_buffer_1ml[name] = RecipeEntry(
                volume=entry.volume * scale_factor,
                stock_concentration=entry.stock_concentration,
                stock_unit=entry.stock_unit,
                final_concentration=entry.final_concentration,
                final_unit=entry.final_unit,
            )

        return result


# =============================================================================
# Parsing Functions
# =============================================================================

def parse_concentration(s: str) -> Tuple[float, str]:
    """
    Parse a concentration string like '50nM', '1.5 mM', '70pmol', or '1.5x'.

    Returns (value, unit) where unit can be:
    - Concentration units: M, mM, uM, nM, %
    - Amount units: pmol, fmol, nmol
    - Ratio: x (e.g., '1.5x' returns (1.5, 'x'))
    """
    s = s.strip()
    match = re.match(r'^([\d.]+)\s*([a-zA-Z%/]+)$', s)
    if not match:
        raise ValueError(f"Invalid concentration format: {s}")
    value = float(match.group(1))
    unit = match.group(2)
    return value, unit


def is_amount_unit(unit: str) -> bool:
    """Check if unit is an absolute amount (pmol, fmol, nmol) rather than concentration."""
    return unit.lower() in ('pmol', 'fmol', 'nmol', 'mol')


def is_ratio_unit(unit: str) -> bool:
    """Check if unit is a ratio (x)."""
    return unit.lower() == 'x'


def convert_amount_to_concentration(amount: float, unit: str, volume_ul: float) -> Tuple[float, str]:
    """
    Convert an absolute amount (pmol, fmol, nmol) to concentration (nM).

    Args:
        amount: The amount value
        unit: The unit (pmol, fmol, nmol)
        volume_ul: The total volume in microliters

    Returns:
        (concentration, unit) tuple in nM
    """
    unit_lower = unit.lower()

    # Convert to pmol first
    if unit_lower == 'fmol':
        pmol = amount / 1000.0
    elif unit_lower == 'pmol':
        pmol = amount
    elif unit_lower == 'nmol':
        pmol = amount * 1000.0
    elif unit_lower == 'mol':
        pmol = amount * 1e12
    else:
        raise ValueError(f"Unknown amount unit: {unit}")

    # Convert pmol to nM: nM = pmol / uL * 1000
    # Actually: pmol / uL = nmol/mL = uM, so pmol / uL * 1000 = nM
    # Wait, let me recalculate:
    # 1 pmol in 1 uL = 1 pmol / 1 uL = 1 pmol / (1e-6 L) = 1e6 pmol/L = 1 uM
    # So: concentration (uM) = pmol / uL
    # concentration (nM) = pmol / uL * 1000
    concentration_nm = (pmol / volume_ul) * 1000.0
    return concentration_nm, 'nM'


def resolve_ratio_amount(ratio: float, reference_amount: float, reference_unit: str) -> Tuple[float, str]:
    """
    Resolve a ratio (e.g., 1.5x) to an absolute amount based on reference.

    Args:
        ratio: The ratio value (e.g., 1.5 for 1.5x)
        reference_amount: The reference amount
        reference_unit: The reference unit

    Returns:
        (amount, unit) tuple
    """
    return ratio * reference_amount, reference_unit


def parse_protein_spec(spec: str, reference_pmol: Optional[float] = None, volume_ul: float = 100.0) -> Protein:
    """
    Parse protein specification string.

    Format: "Name:FinalConc:stock=StockConc[:buffer=Component/Conc,Component/Conc,...]"

    Supports:
    - Concentration: "CDK2:50nM:stock=10uM:buffer=HEPES/20mM,NaCl/150mM"
    - Amount (pmol): "PolII:70pmol:stock=5.17uM:buffer=HEPES/20mM"
    - Ratio: "DSIF:1.5x:stock=50.8uM:buffer=HEPES/20mM" (requires reference_pmol)

    Args:
        spec: The protein specification string
        reference_pmol: Reference amount in pmol for ratio calculations
        volume_ul: Total volume in uL for pmol->concentration conversion
    """
    parts = spec.split(':')
    if len(parts) < 3:
        raise ValueError(f"Invalid protein format: {spec}")

    name = parts[0].strip()

    # Parse final concentration/amount
    final_amount, final_unit = parse_concentration(parts[1])

    # Handle ratio notation (e.g., 1.5x)
    if is_ratio_unit(final_unit):
        if reference_pmol is None:
            raise ValueError(f"Ratio notation '{parts[1]}' requires --reference to be specified")
        # Convert ratio to pmol amount
        final_amount = final_amount * reference_pmol
        final_unit = 'pmol'

    # Convert pmol/fmol/nmol to concentration (nM)
    if is_amount_unit(final_unit):
        final_amount, final_unit = convert_amount_to_concentration(final_amount, final_unit, volume_ul)

    # Parse stock concentration
    stock_part = parts[2].strip()
    if not stock_part.startswith('stock='):
        raise ValueError(f"Expected 'stock=' in protein spec: {spec}")
    stock_amount, stock_unit = parse_concentration(stock_part[6:])

    # Parse buffer components (optional)
    buffer_components = []
    for part in parts[3:]:
        part = part.strip()
        if part.startswith('buffer='):
            buffer_str = part[7:]
            for comp_spec in buffer_str.split(','):
                comp_spec = comp_spec.strip()
                if '/' in comp_spec:
                    comp_name, comp_conc = comp_spec.split('/', 1)
                    conc_value, conc_unit = parse_concentration(comp_conc)
                    buffer_components.append(BufferComponent(
                        name=comp_name.strip(),
                        stock_concentration=conc_value,
                        stock_unit=conc_unit,
                    ))

    return Protein(
        name=name,
        amount=final_amount,
        unit=final_unit,
        stock_concentration=stock_amount,
        stock_unit=stock_unit,
        buffer_components=buffer_components,
    )


def parse_buffer_spec(spec: str) -> BufferComponent:
    """
    Parse buffer component specification string.

    Format: "Name:StockConc->FinalConc"
    Example: "HEPES:1M->25mM"
    """
    if '->' not in spec:
        raise ValueError(f"Invalid buffer format (expected '->'): {spec}")

    left, right = spec.split('->', 1)
    if ':' not in left:
        raise ValueError(f"Invalid buffer format (expected ':'): {spec}")

    name, stock_str = left.rsplit(':', 1)
    stock_value, stock_unit = parse_concentration(stock_str.strip())
    final_value, final_unit = parse_concentration(right.strip())

    return BufferComponent(
        name=name.strip(),
        stock_concentration=stock_value,
        stock_unit=stock_unit,
        final_concentration=final_value,
        final_unit=final_unit,
    )


def load_protein_preset(
    preset_name: str,
    reference_pmol: Optional[float] = None,
    volume_ul: float = 100.0
) -> List[Protein]:
    """
    Load a protein preset by name.

    Supports pmol amounts and ratio notation in presets.
    External presets can define:
    - reference_amount: The reference amount (e.g., 70) with reference_unit (e.g., 'pmol')
    - Proteins with ratio amounts (e.g., amount: 1.5, unit: 'x')
    """
    # Use merged presets (built-in + external)
    presets = MERGED_PROTEIN_PRESETS if MERGED_PROTEIN_PRESETS else PROTEIN_PRESETS
    if preset_name not in presets:
        raise ValueError(f"Unknown protein preset: {preset_name}")

    preset_data = presets[preset_name]

    # Handle preset-level reference (for external presets with ratio support)
    # preset_data could be a list (built-in) or contain reference info (external)
    if isinstance(preset_data, dict):
        protein_list = preset_data.get('proteins', [])
        preset_ref = preset_data.get('reference_amount')
        preset_ref_unit = preset_data.get('reference_unit', 'pmol')
        if preset_ref and reference_pmol is None:
            reference_pmol = preset_ref
    else:
        protein_list = preset_data

    proteins = []
    for p_dict in protein_list:
        # Parse amount - handle pmol and ratio
        amount = p_dict['amount']
        unit = p_dict['unit']

        # Handle ratio notation in preset
        if is_ratio_unit(unit):
            if reference_pmol is None:
                raise ValueError(f"Protein '{p_dict['name']}' uses ratio notation but no reference specified")
            amount = amount * reference_pmol
            unit = 'pmol'

        # Convert pmol/fmol/nmol to concentration
        if is_amount_unit(unit):
            amount, unit = convert_amount_to_concentration(amount, unit, volume_ul)

        buffer_components = []
        for bc in p_dict.get('buffer_components', []):
            buffer_components.append(BufferComponent(
                name=bc['name'],
                stock_concentration=bc['stock_concentration'],
                stock_unit=bc['stock_unit'],
            ))

        proteins.append(Protein(
            name=p_dict['name'],
            amount=amount,
            unit=unit,
            stock_concentration=p_dict['stock_concentration'],
            stock_unit=p_dict['stock_unit'],
            buffer_components=buffer_components,
        ))

    return proteins


def load_buffer_preset(preset_name: str) -> List[BufferComponent]:
    """Load a buffer preset by name."""
    # Use merged presets (built-in + external)
    presets = MERGED_BUFFER_PRESETS if MERGED_BUFFER_PRESETS else BUFFER_PRESETS
    if preset_name not in presets:
        raise ValueError(f"Unknown buffer preset: {preset_name}")

    preset_data = presets[preset_name]

    # Handle external preset format
    if isinstance(preset_data, dict):
        component_list = preset_data.get('components', [])
    else:
        component_list = preset_data

    components = []
    for bc in component_list:
        components.append(BufferComponent(
            name=bc['name'],
            stock_concentration=bc['stock_concentration'],
            stock_unit=bc['stock_unit'],
            final_concentration=bc['final_concentration'],
            final_unit=bc['final_unit'],
        ))

    return components


# =============================================================================
# Output Formatting
# =============================================================================

def format_direct_result(result: DirectRecipeResult, total_volume: float) -> str:
    """Format direct recipe result for display."""
    lines = []

    lines.append("=" * 60)
    lines.append(f"BUFFER RECIPE (Direct Mode) - Total: {total_volume} uL")
    lines.append("=" * 60)

    # Protein volumes
    if result.protein_volumes:
        lines.append("")
        lines.append("PROTEIN STOCKS:")
        lines.append("-" * 40)
        for name, volume in result.protein_volumes.items():
            lines.append(f"  {name:<25} {volume:>8.2f} uL")

    # Buffer contributions
    if result.buffer_contributions:
        lines.append("")
        lines.append("BUFFER CONTRIBUTIONS FROM PROTEINS:")
        lines.append("-" * 40)
        for name, conc in result.buffer_contributions.items():
            if conc > 0:
                lines.append(f"  {name:<25} {conc:>8.3f} mM")

    # Recipe
    lines.append("")
    lines.append("BUFFER COMPONENTS TO ADD:")
    lines.append("-" * 40)
    for name, entry in result.recipe.items():
        if name == 'Water':
            lines.append(f"  {'Water':<25} {entry.volume:>8.2f} uL")
        else:
            stock_info = f"({entry.stock_concentration} {entry.stock_unit} stock)"
            lines.append(
                f"  {name:<25} {entry.volume:>8.2f} uL  {stock_info}"
            )

    # Warnings
    if result.warnings:
        lines.append("")
        lines.append("WARNINGS:")
        lines.append("-" * 40)
        for warning in result.warnings:
            lines.append(f"  ! {warning}")

    lines.append("")
    return '\n'.join(lines)


def format_compensation_result(result: CompensationRecipeResult) -> str:
    """Format compensation buffer result for display."""
    lines = []

    lines.append("=" * 60)
    lines.append(f"COMPENSATION BUFFER ({result.compensation_fold}X)")
    lines.append(f"For reaction volume: {result.total_reaction_volume} uL")
    lines.append("=" * 60)

    # Protein volumes
    if result.protein_volumes:
        lines.append("")
        lines.append("PROTEIN STOCKS (per reaction):")
        lines.append("-" * 40)
        for name, volume in result.protein_volumes.items():
            lines.append(f"  {name:<25} {volume:>8.2f} uL")

    # Compensation buffer recipe
    lines.append("")
    lines.append(f"COMPENSATION BUFFER RECIPE ({result.buffer_volume_needed:.1f} uL per reaction):")
    lines.append("-" * 40)
    for name, entry in result.compensation_buffer.items():
        if name == 'Water':
            lines.append(f"  {'Water':<25} {entry.volume:>8.2f} uL")
        else:
            lines.append(
                f"  {name:<25} {entry.volume:>8.2f} uL  "
                f"({entry.final_concentration:.1f} {entry.final_unit} in buffer)"
            )

    # Scaled to 1 mL
    lines.append("")
    lines.append("SCALED TO 1 mL:")
    lines.append("-" * 40)
    for name, entry in result.compensation_buffer_1ml.items():
        if name == 'Water':
            lines.append(f"  {'Water':<25} {entry.volume:>8.2f} uL")
        else:
            lines.append(f"  {name:<25} {entry.volume:>8.2f} uL")

    # Warnings
    if result.warnings:
        lines.append("")
        lines.append("WARNINGS:")
        lines.append("-" * 40)
        for warning in result.warnings:
            lines.append(f"  ! {warning}")

    lines.append("")
    return '\n'.join(lines)


def result_to_dict(result) -> dict:
    """Convert result to dictionary for JSON output."""
    if isinstance(result, DirectRecipeResult):
        recipe = {}
        for name, entry in result.recipe.items():
            recipe[name] = {
                'volume': entry.volume,
                'stock_concentration': entry.stock_concentration,
                'stock_unit': entry.stock_unit,
                'final_concentration': entry.final_concentration,
                'final_unit': entry.final_unit,
            }
        return {
            'mode': 'direct',
            'recipe': recipe,
            'protein_volumes': result.protein_volumes,
            'buffer_contributions': result.buffer_contributions,
            'total_calculated_volume': result.total_calculated_volume,
            'warnings': result.warnings,
        }
    elif isinstance(result, CompensationRecipeResult):
        buffer = {}
        for name, entry in result.compensation_buffer.items():
            buffer[name] = {
                'volume': entry.volume,
                'stock_concentration': entry.stock_concentration,
                'stock_unit': entry.stock_unit,
                'final_concentration': entry.final_concentration,
                'final_unit': entry.final_unit,
            }
        buffer_1ml = {}
        for name, entry in result.compensation_buffer_1ml.items():
            buffer_1ml[name] = {
                'volume': entry.volume,
                'stock_concentration': entry.stock_concentration,
                'stock_unit': entry.stock_unit,
                'final_concentration': entry.final_concentration,
                'final_unit': entry.final_unit,
            }
        return {
            'mode': 'compensation',
            'compensation_fold': result.compensation_fold,
            'compensation_buffer': buffer,
            'compensation_buffer_1ml': buffer_1ml,
            'protein_volumes': result.protein_volumes,
            'buffer_volume_needed': result.buffer_volume_needed,
            'total_reaction_volume': result.total_reaction_volume,
            'warnings': result.warnings,
        }
    return {}


# =============================================================================
# CLI
# =============================================================================

def list_presets():
    """Print available presets (merged built-in + external)."""
    presets = MERGED_PROTEIN_PRESETS if MERGED_PROTEIN_PRESETS else PROTEIN_PRESETS
    buffer_presets = MERGED_BUFFER_PRESETS if MERGED_BUFFER_PRESETS else BUFFER_PRESETS

    print("PROTEIN PRESETS:")
    print("-" * 40)
    for name, preset_data in presets.items():
        # Handle both list format (built-in) and dict format (external)
        if isinstance(preset_data, dict):
            proteins = preset_data.get('proteins', [])
        else:
            proteins = preset_data
        protein_names = [p['name'] for p in proteins]
        print(f"  {name:<20} {', '.join(protein_names)}")

    print("")
    print("BUFFER PRESETS:")
    print("-" * 40)
    for name, preset_data in buffer_presets.items():
        # Handle both list format (built-in) and dict format (external)
        if isinstance(preset_data, dict):
            components = preset_data.get('components', [])
        else:
            components = preset_data
        comp_summary = [f"{c['name']}/{c['final_concentration']}{c['final_unit']}" for c in components[:3]]
        if len(components) > 3:
            comp_summary.append("...")
        print(f"  {name:<20} {', '.join(comp_summary)}")


def list_stocks():
    """Print predefined stock concentrations."""
    print("PREDEFINED STOCK CONCENTRATIONS:")
    print("-" * 40)
    for name, (conc, unit) in sorted(PREDEFINED_STOCKS.items()):
        print(f"  {name:<15} {conc} {unit}")


def parse_reference(ref_str: str) -> float:
    """Parse reference amount string (e.g., '70pmol') to pmol value."""
    amount, unit = parse_concentration(ref_str)
    unit_lower = unit.lower()

    if unit_lower == 'fmol':
        return amount / 1000.0
    elif unit_lower == 'pmol':
        return amount
    elif unit_lower == 'nmol':
        return amount * 1000.0
    else:
        raise ValueError(f"Reference must be in pmol, fmol, or nmol, got: {unit}")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate buffer recipes accounting for protein stock contributions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List presets and stocks
  %(prog)s --list-presets
  %(prog)s --list-stocks

  # Use presets
  %(prog)s --protein-preset kinase_panel --buffer-preset kinase_assay --volume 100

  # Direct specification with concentration
  %(prog)s --protein "CDK2:50nM:stock=10uM:buffer=HEPES/20mM,NaCl/150mM" \\
           --buffer "HEPES:1M->25mM" --buffer "NaCl:5M->100mM" --volume 100

  # Using pmol amounts (automatically converted to concentration)
  %(prog)s --protein "PolII:70pmol:stock=5.17uM:buffer=HEPES/20mM,NaCl/150mM" \\
           --buffer "HEPES:1M->20mM" --volume 100

  # Using molar ratios with reference
  %(prog)s --reference 70pmol \\
           --protein "PolII:1x:stock=5.17uM:buffer=HEPES/20mM" \\
           --protein "DSIF:1.5x:stock=50.8uM:buffer=HEPES/20mM" \\
           --buffer "HEPES:1M->20mM" --volume 100

  # Compensation buffer mode
  %(prog)s --protein-preset purification_stocks --buffer-preset storage \\
           --volume 100 --mode compensation --fold 10

  # Load presets from external YAML file
  %(prog)s --presets-file my_presets.yaml --protein-preset my_complex
        """
    )

    parser.add_argument('--protein', '-p', action='append', default=[],
                        metavar='SPEC',
                        help='Protein spec: "Name:Amount:stock=StockConc[:buffer=Comp/Conc,...]". '
                             'Amount can be concentration (50nM), absolute (70pmol), or ratio (1.5x)')
    parser.add_argument('--buffer', '-b', action='append', default=[],
                        metavar='SPEC',
                        help='Buffer component: "Name:StockConc->FinalConc"')
    parser.add_argument('--protein-preset', metavar='NAME',
                        help='Use a predefined protein preset')
    parser.add_argument('--buffer-preset', metavar='NAME',
                        help='Use a predefined buffer preset')
    parser.add_argument('--reference', '-r', metavar='AMOUNT',
                        help='Reference amount for ratio calculations (e.g., 70pmol)')
    parser.add_argument('--presets-file', metavar='FILE',
                        help='Path to external YAML/JSON presets file')
    parser.add_argument('--volume', '-v', type=float, default=100,
                        help='Total reaction volume in uL (default: 100)')
    parser.add_argument('--mode', '-m', choices=['direct', 'compensation'],
                        default='direct',
                        help='Calculation mode (default: direct)')
    parser.add_argument('--fold', '-f', type=int, default=10,
                        help='Compensation buffer fold (default: 10)')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    parser.add_argument('--list-presets', action='store_true',
                        help='List available presets')
    parser.add_argument('--list-stocks', action='store_true',
                        help='List predefined stock concentrations')

    args = parser.parse_args()

    # Initialize merged presets (built-in + external)
    preset_file = Path(args.presets_file) if args.presets_file else None
    init_merged_presets(preset_file)

    # Handle info commands
    if args.list_presets:
        list_presets()
        return 0

    if args.list_stocks:
        list_stocks()
        return 0

    # Parse reference amount if provided
    reference_pmol = None
    if args.reference:
        try:
            reference_pmol = parse_reference(args.reference)
        except ValueError as e:
            print(f"Error parsing reference: {e}", file=sys.stderr)
            return 1

    # Build protein list
    proteins: List[Protein] = []

    if args.protein_preset:
        try:
            proteins.extend(load_protein_preset(
                args.protein_preset,
                reference_pmol=reference_pmol,
                volume_ul=args.volume
            ))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    for spec in args.protein:
        try:
            proteins.append(parse_protein_spec(
                spec,
                reference_pmol=reference_pmol,
                volume_ul=args.volume
            ))
        except ValueError as e:
            print(f"Error parsing protein: {e}", file=sys.stderr)
            return 1

    # Build buffer component list
    buffer_components: List[BufferComponent] = []

    if args.buffer_preset:
        try:
            buffer_components.extend(load_buffer_preset(args.buffer_preset))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    for spec in args.buffer:
        try:
            buffer_components.append(parse_buffer_spec(spec))
        except ValueError as e:
            print(f"Error parsing buffer: {e}", file=sys.stderr)
            return 1

    # Validate inputs
    if not proteins:
        print("Error: At least one protein is required (use --protein or --protein-preset)",
              file=sys.stderr)
        return 1

    if not buffer_components:
        print("Error: At least one buffer component is required (use --buffer or --buffer-preset)",
              file=sys.stderr)
        return 1

    # Calculate
    calculator = BufferCalculator()

    try:
        if args.mode == 'direct':
            result = calculator.calculate_direct_recipe(
                proteins, buffer_components, args.volume
            )
            if args.json:
                print(json.dumps(result_to_dict(result), indent=2))
            else:
                print(format_direct_result(result, args.volume))

        elif args.mode == 'compensation':
            result = calculator.calculate_compensation_buffer(
                proteins, buffer_components, args.volume, args.fold
            )
            if args.json:
                print(json.dumps(result_to_dict(result), indent=2))
            else:
                print(format_compensation_result(result))

    except Exception as e:
        print(f"Error during calculation: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
