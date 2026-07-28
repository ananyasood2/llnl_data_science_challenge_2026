import { useCallback, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { classifyDefects } from '../api/dashboardApi.js';

export function useClassifyDefects() {
  const queryClient = useQueryClient();
  const latestRequestIdRef = useRef(0);
  const {
    mutate,
    reset,
    ...mutationState
  } = useMutation({
    mutationFn: ({ thresholds }) => classifyDefects(thresholds),
  });

  const classify = useCallback((thresholds, callbacks = {}) => {
    const requestId = latestRequestIdRef.current + 1;
    latestRequestIdRef.current = requestId;
    reset();
    mutate(
      { thresholds, requestId },
      {
        onSuccess: (classificationResult, variables) => {
          if (variables.requestId !== latestRequestIdRef.current) return;
          queryClient.setQueryData(['defects'], classificationResult);
          callbacks.onSuccess?.(classificationResult);
        },
        onError: (error, variables) => {
          if (variables.requestId !== latestRequestIdRef.current) return;
          callbacks.onError?.(error);
        },
      },
    );
  }, [mutate, queryClient, reset]);

  return {
    ...mutationState,
    classify,
  };
}
