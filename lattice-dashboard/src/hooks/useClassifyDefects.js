import { useMutation, useQueryClient } from '@tanstack/react-query';
import { classifyDefects } from '../api/dashboardApi.js';
import { useDefectStore } from '../store/useDefectStore.js';

export function useClassifyDefects() {
  const queryClient = useQueryClient();
  const missingOccupancyThreshold = useDefectStore(
    (state) => state.missing_occupancy_threshold,
  );
  const brokenGapThreshold = useDefectStore((state) => state.broken_gap_threshold);
  const thinOccupancyThreshold = useDefectStore(
    (state) => state.thin_occupancy_threshold,
  );

  const thresholds = {
    missing_occupancy_threshold: missingOccupancyThreshold,
    broken_gap_threshold: brokenGapThreshold,
    thin_occupancy_threshold: thinOccupancyThreshold,
  };

  return useMutation({
    mutationFn: () => classifyDefects(thresholds),
    onSuccess: (classificationResult) => {
      queryClient.setQueryData(['defects'], classificationResult);
    },
  });
}
