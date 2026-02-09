#!/usr/bin/env python3
"""
Gel Image Analyzer CLI - Analyze SDS-PAGE gel images

Usage:
    gel_analyzer_cli.py <image_path> --ladder-lane <N>        Analyze gel with ladder in lane N
    gel_analyzer_cli.py <image_path> --ladder-lane <N> --expect "Protein:45kDa"
    gel_analyzer_cli.py --list-ladders                        List available ladder presets

Features:
    - Auto-detect lanes and bands
    - Estimate molecular weight using ladder calibration
    - Compare detected bands to expected MW
"""

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from scipy import signal
    from scipy import ndimage
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


# =============================================================================
# Ladder Presets (MW in kDa, ordered from high to low)
# =============================================================================

LADDER_PRESETS = {
    "pageruler": {
        "name": "PageRuler Prestained (Thermo)",
        "mw": [250, 130, 95, 72, 55, 36, 28, 17, 10],
        "description": "Thermo Scientific PageRuler Prestained Protein Ladder"
    },
    "pageruler_plus": {
        "name": "PageRuler Plus Prestained (Thermo)",
        "mw": [250, 130, 100, 70, 55, 35, 25, 15, 10],
        "description": "Thermo Scientific PageRuler Plus Prestained Protein Ladder"
    },
    "precision_plus": {
        "name": "Precision Plus Dual Color (Bio-Rad)",
        "mw": [250, 150, 100, 75, 50, 37, 25, 20, 15, 10],
        "description": "Bio-Rad Precision Plus Protein Dual Color Standards"
    },
    "neb_broad": {
        "name": "Color Prestained Broad Range (NEB)",
        "mw": [245, 180, 135, 100, 75, 63, 48, 35, 25, 17, 11],
        "description": "NEB Color Prestained Protein Standard, Broad Range"
    },
    "benchmark": {
        "name": "BenchMark Prestained (Invitrogen)",
        "mw": [220, 160, 120, 100, 90, 80, 70, 60, 50, 40, 30, 25, 20, 15, 10],
        "description": "Invitrogen BenchMark Prestained Protein Ladder"
    },
    "spectra_multicolor": {
        "name": "Spectra Multicolor Broad Range (Thermo)",
        "mw": [260, 140, 100, 70, 50, 40, 35, 25, 15, 10],
        "description": "Thermo Scientific Spectra Multicolor Broad Range Protein Ladder"
    }
}

# Sensitivity presets for band detection
SENSITIVITY_PRESETS = {
    "low": {"prominence": 0.15, "height": 0.2, "distance": 15},
    "medium": {"prominence": 0.08, "height": 0.1, "distance": 10},
    "high": {"prominence": 0.04, "height": 0.05, "distance": 5}
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Band:
    """Represents a detected band in a lane."""
    position: int  # Row position in pixels
    intensity: float  # Relative intensity (0-1)
    mw_kda: Optional[float] = None  # Estimated MW in kDa
    width: int = 0  # Band width in pixels
    match: Optional[str] = None  # Name of matched expected protein


@dataclass
class Lane:
    """Represents a detected lane in the gel."""
    number: int  # 1-indexed lane number
    left: int  # Left boundary in pixels
    right: int  # Right boundary in pixels
    center: int  # Center position in pixels
    bands: List[Band] = field(default_factory=list)
    is_ladder: bool = False


@dataclass
class GelAnalysisResult:
    """Complete analysis result for a gel image."""
    image_path: str
    image_width: int
    image_height: int
    num_lanes: int
    lanes: List[Lane]
    ladder_lane: Optional[int]
    ladder_type: Optional[str]
    calibration_r2: Optional[float]
    expected_proteins: List[Dict[str, Any]]
    matches_found: int
    total_bands: int


# =============================================================================
# Image Processing Functions
# =============================================================================

def load_gel_image(image_path: str) -> np.ndarray:
    """Load gel image and convert to normalized grayscale array."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = Image.open(path)

    # Convert to grayscale if needed
    if img.mode != 'L':
        img = img.convert('L')

    # Convert to numpy array
    arr = np.array(img, dtype=np.float64)

    # Normalize to 0-1 range
    arr = arr / 255.0

    return arr


def preprocess_image(arr: np.ndarray) -> np.ndarray:
    """Preprocess gel image for analysis."""
    # Determine if image is inverted (dark bands on light background)
    # Most gels have dark bands on light background after Coomassie staining
    mean_intensity = np.mean(arr)

    # If mostly bright, invert so bands appear as peaks
    if mean_intensity > 0.5:
        arr = 1.0 - arr

    # Apply slight Gaussian smoothing to reduce noise
    arr = ndimage.gaussian_filter(arr, sigma=1.0)

    # Normalize intensity
    arr_min = np.min(arr)
    arr_max = np.max(arr)
    if arr_max > arr_min:
        arr = (arr - arr_min) / (arr_max - arr_min)

    return arr


def get_column_profile(arr: np.ndarray) -> np.ndarray:
    """Get intensity profile across columns (for lane detection)."""
    return np.mean(arr, axis=0)


def get_row_profile(arr: np.ndarray, left: int, right: int) -> np.ndarray:
    """Get intensity profile across rows for a specific lane region."""
    lane_region = arr[:, left:right]
    return np.mean(lane_region, axis=1)


# =============================================================================
# Lane Detection
# =============================================================================

def detect_lanes(arr: np.ndarray, num_lanes: Optional[int] = None,
                 min_lane_width: int = 20) -> List[Lane]:
    """Auto-detect lanes in gel image."""
    height, width = arr.shape
    column_profile = get_column_profile(arr)

    # Smooth the profile
    smoothed = ndimage.gaussian_filter1d(column_profile, sigma=5)

    if num_lanes is not None:
        # User specified number of lanes - divide evenly
        lane_width = width // num_lanes
        lanes = []
        for i in range(num_lanes):
            left = i * lane_width
            right = min((i + 1) * lane_width, width)
            center = (left + right) // 2
            lanes.append(Lane(
                number=i + 1,
                left=left,
                right=right,
                center=center
            ))
        return lanes

    # Auto-detect lanes by finding intensity peaks (lane centers)
    # Lanes appear as vertical bright stripes (after preprocessing)

    # Find peaks in column profile (these are lane centers)
    # Use adaptive parameters based on image width
    expected_lanes = max(3, width // 80)  # Rough estimate
    min_distance = max(min_lane_width, width // (expected_lanes * 2))

    peaks, properties = signal.find_peaks(
        smoothed,
        distance=min_distance,
        prominence=0.05,
        height=np.mean(smoothed)
    )

    if len(peaks) < 2:
        # Fallback: try with less strict parameters
        peaks, properties = signal.find_peaks(
            smoothed,
            distance=min_lane_width,
            prominence=0.02
        )

    if len(peaks) == 0:
        # Last resort: divide image into reasonable number of lanes
        num_lanes = max(1, width // 60)
        return detect_lanes(arr, num_lanes=num_lanes)

    # Convert peaks to lane boundaries
    lanes = []
    for i, peak in enumerate(peaks):
        # Determine lane boundaries
        if i == 0:
            left = max(0, peak - min_distance // 2)
        else:
            left = (peaks[i - 1] + peak) // 2

        if i == len(peaks) - 1:
            right = min(width, peak + min_distance // 2)
        else:
            right = (peak + peaks[i + 1]) // 2

        lanes.append(Lane(
            number=i + 1,
            left=left,
            right=right,
            center=peak
        ))

    return lanes


# =============================================================================
# Band Detection
# =============================================================================

def detect_bands(arr: np.ndarray, lane: Lane,
                 sensitivity: str = "medium") -> List[Band]:
    """Detect bands within a lane."""
    params = SENSITIVITY_PRESETS.get(sensitivity, SENSITIVITY_PRESETS["medium"])

    # Get row intensity profile for this lane
    row_profile = get_row_profile(arr, lane.left, lane.right)

    # Smooth the profile
    smoothed = ndimage.gaussian_filter1d(row_profile, sigma=2)

    # Find peaks (bands)
    peaks, properties = signal.find_peaks(
        smoothed,
        prominence=params["prominence"],
        height=params["height"],
        distance=params["distance"],
        width=2
    )

    bands = []
    for i, peak in enumerate(peaks):
        intensity = smoothed[peak]

        # Estimate band width from peak properties if available
        width = 5
        if "widths" in properties and i < len(properties["widths"]):
            width = int(properties["widths"][i])

        bands.append(Band(
            position=peak,
            intensity=intensity,
            width=width
        ))

    # Sort bands by position (top to bottom = high MW to low MW)
    bands.sort(key=lambda b: b.position)

    return bands


# =============================================================================
# MW Calibration
# =============================================================================

def calibrate_mw(ladder_bands: List[Band], ladder_mw: List[float]) -> Tuple[Optional[callable], float]:
    """
    Calibrate MW estimation using ladder bands.
    Returns a function that converts pixel position to MW, and R² value.
    """
    if len(ladder_bands) < 2:
        return None, 0.0

    # Match detected bands to known MW values
    # Assume bands are in order (top = high MW, bottom = low MW)
    num_bands = min(len(ladder_bands), len(ladder_mw))

    positions = [b.position for b in ladder_bands[:num_bands]]
    mw_values = ladder_mw[:num_bands]

    # Use log10(MW) for linear fit (semi-log relationship)
    log_mw = [math.log10(mw) for mw in mw_values]

    # Linear regression: log(MW) = a * position + b
    n = len(positions)
    sum_x = sum(positions)
    sum_y = sum(log_mw)
    sum_xy = sum(p * lm for p, lm in zip(positions, log_mw))
    sum_x2 = sum(p * p for p in positions)

    # Calculate slope and intercept
    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-10:
        return None, 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # Calculate R²
    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in log_mw)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(positions, log_mw))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    # Create calibration function
    def estimate_mw(position: int) -> float:
        log_mw_est = slope * position + intercept
        return 10 ** log_mw_est

    # Assign MW to ladder bands
    for band in ladder_bands[:num_bands]:
        band.mw_kda = estimate_mw(band.position)

    return estimate_mw, r2


def apply_mw_calibration(lanes: List[Lane], estimate_mw: callable):
    """Apply MW calibration to all bands in all lanes."""
    for lane in lanes:
        if not lane.is_ladder:
            for band in lane.bands:
                band.mw_kda = estimate_mw(band.position)


# =============================================================================
# Expected MW Comparison
# =============================================================================

def parse_expected_protein(spec: str) -> Dict[str, Any]:
    """Parse expected protein specification like 'ProteinName:45kDa'."""
    match = re.match(r'^([^:]+):(\d+(?:\.\d+)?)\s*k?[Dd]?[Aa]?$', spec.strip())
    if not match:
        raise ValueError(f"Invalid expected protein format: {spec}. Use 'Name:MWkDa' format.")

    return {
        "name": match.group(1).strip(),
        "mw_kda": float(match.group(2))
    }


def calculate_mw_from_sequence(sequence: str) -> float:
    """Calculate MW from amino acid sequence."""
    # Amino acid molecular weights (average)
    AA_MW = {
        'A': 89.09, 'R': 174.20, 'N': 132.12, 'D': 133.10, 'C': 121.15,
        'E': 147.13, 'Q': 146.15, 'G': 75.07, 'H': 155.16, 'I': 131.17,
        'L': 131.17, 'K': 146.19, 'M': 149.21, 'F': 165.19, 'P': 115.13,
        'S': 105.09, 'T': 119.12, 'W': 204.23, 'Y': 181.19, 'V': 117.15
    }
    WATER_MW = 18.015

    sequence = sequence.upper().replace(" ", "").replace("\n", "")
    mw = sum(AA_MW.get(aa, 0) for aa in sequence)

    # Subtract water for peptide bonds
    if len(sequence) > 0:
        mw -= (len(sequence) - 1) * WATER_MW

    return mw / 1000  # Convert to kDa


def match_expected_proteins(lanes: List[Lane], expected: List[Dict[str, Any]],
                           tolerance: float = 0.10) -> int:
    """Match detected bands to expected proteins within tolerance."""
    matches = 0

    for protein in expected:
        expected_mw = protein["mw_kda"]
        protein_name = protein["name"]

        # Search all non-ladder lanes for a matching band
        best_match = None
        best_diff = float('inf')

        for lane in lanes:
            if lane.is_ladder:
                continue

            for band in lane.bands:
                if band.mw_kda is None:
                    continue

                diff = abs(band.mw_kda - expected_mw) / expected_mw
                if diff <= tolerance and diff < best_diff:
                    best_match = band
                    best_diff = diff

        if best_match:
            best_match.match = protein_name
            matches += 1

    return matches


# =============================================================================
# Output Formatting
# =============================================================================

def format_text_output(result: GelAnalysisResult) -> str:
    """Format analysis result as text."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"GEL ANALYSIS: {Path(result.image_path).name}")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Image size: {result.image_width} x {result.image_height} pixels")
    lines.append(f"Detected {result.num_lanes} lanes")
    lines.append("")

    if result.ladder_lane and result.ladder_type:
        ladder_info = LADDER_PRESETS.get(result.ladder_type, {})
        lines.append(f"Ladder: {ladder_info.get('name', result.ladder_type)} (Lane {result.ladder_lane})")
        if result.calibration_r2 is not None:
            lines.append(f"Calibration R²: {result.calibration_r2:.4f}")
        lines.append("")

    # Output each lane
    for lane in result.lanes:
        if lane.is_ladder:
            lines.append(f"LADDER (Lane {lane.number}):")
        else:
            lines.append(f"LANE {lane.number}:")

        if not lane.bands:
            lines.append("  No bands detected")
        else:
            for i, band in enumerate(lane.bands, 1):
                mw_str = f"{band.mw_kda:.1f} kDa" if band.mw_kda else "? kDa"
                intensity_str = f"intensity: {band.intensity:.2f}"

                match_str = ""
                if band.match:
                    match_str = f" <- matches {band.match}"

                lines.append(f"  Band {i}: ~{mw_str:>10} (row {band.position:4d}, {intensity_str}){match_str}")

        lines.append("")

    # Summary
    lines.append("-" * 40)
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Total bands detected: {result.total_bands}")

    if result.expected_proteins:
        lines.append(f"Expected proteins: {len(result.expected_proteins)}")
        lines.append(f"Matches found: {result.matches_found}/{len(result.expected_proteins)}")

    return "\n".join(lines)


def format_json_output(result: GelAnalysisResult) -> str:
    """Format analysis result as JSON."""
    # Helper to convert numpy types to Python native types
    def to_native(val):
        if hasattr(val, 'item'):  # numpy scalar
            return val.item()
        return val

    output = {
        "image": result.image_path,
        "image_width": to_native(result.image_width),
        "image_height": to_native(result.image_height),
        "num_lanes": result.num_lanes,
        "ladder": {
            "lane": result.ladder_lane,
            "type": result.ladder_type,
            "calibration_r2": round(result.calibration_r2, 4) if result.calibration_r2 else None
        } if result.ladder_lane else None,
        "lanes": [],
        "expected_proteins": result.expected_proteins,
        "matches_found": result.matches_found,
        "total_bands": result.total_bands
    }

    for lane in result.lanes:
        lane_data = {
            "number": lane.number,
            "left": to_native(lane.left),
            "right": to_native(lane.right),
            "center": to_native(lane.center),
            "is_ladder": lane.is_ladder,
            "bands": [
                {
                    "position": to_native(b.position),
                    "mw_kda": round(b.mw_kda, 2) if b.mw_kda else None,
                    "intensity": round(float(b.intensity), 3),
                    "width": to_native(b.width),
                    "match": b.match
                }
                for b in lane.bands
            ]
        }
        output["lanes"].append(lane_data)

    return json.dumps(output, indent=2)


def list_ladders() -> str:
    """List available ladder presets."""
    lines = []
    lines.append("Available Ladder Presets:")
    lines.append("=" * 60)
    lines.append("")

    for key, preset in LADDER_PRESETS.items():
        lines.append(f"  {key}")
        lines.append(f"    Name: {preset['name']}")
        lines.append(f"    MW bands (kDa): {', '.join(str(m) for m in preset['mw'])}")
        lines.append(f"    Description: {preset['description']}")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# Main Analysis Function
# =============================================================================

def analyze_gel(
    image_path: str,
    ladder_lane: int,
    ladder_type: str = "pageruler",
    expected_proteins: Optional[List[str]] = None,
    sequences: Optional[List[str]] = None,
    num_lanes: Optional[int] = None,
    sensitivity: str = "medium",
    mw_tolerance: float = 0.10
) -> GelAnalysisResult:
    """Perform complete gel analysis."""

    # Load and preprocess image
    arr = load_gel_image(image_path)
    arr = preprocess_image(arr)
    height, width = arr.shape

    # Detect lanes
    lanes = detect_lanes(arr, num_lanes=num_lanes)

    # Validate ladder lane
    if ladder_lane < 1 or ladder_lane > len(lanes):
        raise ValueError(f"Ladder lane {ladder_lane} is out of range (1-{len(lanes)})")

    # Mark ladder lane
    lanes[ladder_lane - 1].is_ladder = True

    # Detect bands in all lanes
    for lane in lanes:
        lane.bands = detect_bands(arr, lane, sensitivity=sensitivity)

    # Get ladder preset
    if ladder_type not in LADDER_PRESETS:
        raise ValueError(f"Unknown ladder type: {ladder_type}. Use --list-ladders to see available presets.")

    ladder_mw = LADDER_PRESETS[ladder_type]["mw"]

    # Calibrate MW using ladder
    ladder_bands = lanes[ladder_lane - 1].bands
    estimate_mw, r2 = calibrate_mw(ladder_bands, ladder_mw)

    if estimate_mw is None:
        print("Warning: Could not calibrate MW. Too few bands detected in ladder lane.",
              file=sys.stderr)

    # Apply calibration to all lanes
    if estimate_mw:
        apply_mw_calibration(lanes, estimate_mw)

    # Parse expected proteins
    parsed_expected = []
    if expected_proteins:
        for spec in expected_proteins:
            try:
                parsed_expected.append(parse_expected_protein(spec))
            except ValueError as e:
                print(f"Warning: {e}", file=sys.stderr)

    # Add proteins from sequences
    if sequences:
        for i, seq in enumerate(sequences):
            mw = calculate_mw_from_sequence(seq)
            parsed_expected.append({
                "name": f"Sequence_{i+1}",
                "mw_kda": mw
            })

    # Match expected proteins
    matches_found = 0
    if parsed_expected and estimate_mw:
        matches_found = match_expected_proteins(lanes, parsed_expected, tolerance=mw_tolerance)

    # Count total bands
    total_bands = sum(len(lane.bands) for lane in lanes)

    return GelAnalysisResult(
        image_path=image_path,
        image_width=width,
        image_height=height,
        num_lanes=len(lanes),
        lanes=lanes,
        ladder_lane=ladder_lane,
        ladder_type=ladder_type,
        calibration_r2=r2 if estimate_mw else None,
        expected_proteins=parsed_expected,
        matches_found=matches_found,
        total_bands=total_bands
    )


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Gel Image Analyzer - Analyze SDS-PAGE gel images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s gel.png --ladder-lane 1
  %(prog)s gel.png --ladder-lane 1 --ladder precision_plus
  %(prog)s gel.png --ladder-lane 1 --expect "BSA:66.5kDa" --expect "TFIIB:38kDa"
  %(prog)s gel.png --ladder-lane 8 --sensitivity high --json
  %(prog)s --list-ladders
        """
    )

    parser.add_argument("image", nargs="?", help="Path to gel image file")
    parser.add_argument("--ladder-lane", "-l", type=int,
                        help="Lane number containing MW ladder (1-indexed)")
    parser.add_argument("--ladder", "-t", default="pageruler",
                        help="Ladder preset name (default: pageruler)")
    parser.add_argument("--expect", "-e", action="append", dest="expected",
                        help="Expected protein with MW, e.g., 'Protein:45kDa' (repeatable)")
    parser.add_argument("--sequence", "-s", action="append", dest="sequences",
                        help="Protein sequence to calculate expected MW (repeatable)")
    parser.add_argument("--lanes", "-n", type=int,
                        help="Override auto-detection with specific lane count")
    parser.add_argument("--sensitivity", choices=["low", "medium", "high"],
                        default="medium", help="Band detection sensitivity (default: medium)")
    parser.add_argument("--tolerance", type=float, default=0.10,
                        help="MW matching tolerance as fraction (default: 0.10 = 10%%)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--list-ladders", action="store_true",
                        help="List available ladder presets")

    args = parser.parse_args()

    # Check dependencies
    if not PIL_AVAILABLE:
        print("Error: Pillow is required. Install with: pip3 install Pillow", file=sys.stderr)
        return 1

    if not NUMPY_AVAILABLE:
        print("Error: NumPy is required. Install with: pip3 install numpy", file=sys.stderr)
        return 1

    if not SCIPY_AVAILABLE:
        print("Error: SciPy is required. Install with: pip3 install scipy", file=sys.stderr)
        return 1

    # Handle --list-ladders
    if args.list_ladders:
        print(list_ladders())
        return 0

    # Validate required arguments for analysis
    if not args.image:
        parser.error("Image path is required")

    if not args.ladder_lane:
        parser.error("--ladder-lane is required to specify which lane contains the MW ladder")

    try:
        result = analyze_gel(
            image_path=args.image,
            ladder_lane=args.ladder_lane,
            ladder_type=args.ladder,
            expected_proteins=args.expected,
            sequences=args.sequences,
            num_lanes=args.lanes,
            sensitivity=args.sensitivity,
            mw_tolerance=args.tolerance
        )

        if args.json:
            print(format_json_output(result))
        else:
            print(format_text_output(result))

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
