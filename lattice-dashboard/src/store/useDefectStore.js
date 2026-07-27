import { create } from 'zustand';

export const DEFAULT_CLASSIFICATION_THRESHOLDS = Object.freeze({
  missing_occupancy_threshold: 0.05,
  broken_gap_threshold: 0.8,
  thin_occupancy_threshold: 0.6,
});

function asFiniteNumber(value, fallback) {
  const parsedValue = Number(value);
  return Number.isFinite(parsedValue) ? parsedValue : fallback;
}

export const useDefectStore = create((set) => ({
  ...DEFAULT_CLASSIFICATION_THRESHOLDS,
  activeFilter: 'ALL',

  setMissingOccupancyThreshold: (value) =>
    set({
      missing_occupancy_threshold: asFiniteNumber(
        value,
        DEFAULT_CLASSIFICATION_THRESHOLDS.missing_occupancy_threshold,
      ),
    }),

  setBrokenGapThreshold: (value) =>
    set({
      broken_gap_threshold: asFiniteNumber(
        value,
        DEFAULT_CLASSIFICATION_THRESHOLDS.broken_gap_threshold,
      ),
    }),

  setThinOccupancyThreshold: (value) =>
    set({
      thin_occupancy_threshold: asFiniteNumber(
        value,
        DEFAULT_CLASSIFICATION_THRESHOLDS.thin_occupancy_threshold,
      ),
    }),

  setThresholds: (thresholds) =>
    set((state) => ({
      missing_occupancy_threshold: asFiniteNumber(
        thresholds?.missing_occupancy_threshold,
        state.missing_occupancy_threshold,
      ),
      broken_gap_threshold: asFiniteNumber(
        thresholds?.broken_gap_threshold,
        state.broken_gap_threshold,
      ),
      thin_occupancy_threshold: asFiniteNumber(
        thresholds?.thin_occupancy_threshold,
        state.thin_occupancy_threshold,
      ),
    })),

  setActiveFilter: (activeFilter) => set({ activeFilter }),
}));
