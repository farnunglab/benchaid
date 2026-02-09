package main

import "testing"

func TestParseRegionRange(t *testing.T) {
	rng, name, err := parseRegion("10-200")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if name != "" {
		t.Fatalf("expected empty name, got %q", name)
	}
	if rng == nil || rng.Start != 10 || rng.End != 200 {
		t.Fatalf("unexpected range: %+v", rng)
	}
}

func TestComputeDisorderedRegions(t *testing.T) {
	plddt := []float64{80, 40, 30, 90, 60, 49}
	disorder := computeDisorderedRegions(plddt, len(plddt))
	expected := []bool{false, true, true, false, false, true}
	if len(disorder) != len(expected) {
		t.Fatalf("unexpected length: %d", len(disorder))
	}
	for i := range expected {
		if disorder[i] != expected[i] {
			t.Fatalf("position %d mismatch: got %v, want %v", i, disorder[i], expected[i])
		}
	}
}
