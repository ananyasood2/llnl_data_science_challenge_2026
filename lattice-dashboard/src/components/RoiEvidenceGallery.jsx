import { useEffect, useState } from 'react';

const API_ORIGIN = 'http://localhost:8000';
const FALLBACK_WARNING =
  'Note: Thresholds are currently uncalibrated. Defects shown are provisional candidates.';

const IMAGE_DETAILS = [
  { key: 'xy_overlay', label: 'XY', description: 'Cross-section at the strut midpoint Z plane.' },
  { key: 'xz_overlay', label: 'XZ', description: 'Cross-section at the strut midpoint Y plane.' },
  { key: 'yz_overlay', label: 'YZ', description: 'Cross-section at the strut midpoint X plane.' },
];

function formatCoordinates(values) {
  return Array.isArray(values) ? values.join(', ') : 'Unavailable';
}

export default function RoiEvidenceGallery({ selectedStrutId }) {
  const [requestVersion, setRequestVersion] = useState(0);
  const [galleryState, setGalleryState] = useState({
    status: 'idle',
    strutId: null,
    data: null,
    error: null,
  });
  const [expandedImage, setExpandedImage] = useState(null);

  useEffect(() => {
    if (selectedStrutId === null || selectedStrutId === undefined) {
      return undefined;
    }

    const controller = new AbortController();
    let isCurrent = true;

    async function loadRoiEvidence() {
      setGalleryState({ status: 'loading', strutId: selectedStrutId, data: null, error: null });
      try {
        const response = await fetch(`${API_ORIGIN}/api/struts/${selectedStrutId}/roi`, {
          method: 'POST',
          signal: controller.signal,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.detail || 'Unable to generate local ROI evidence.');
        }
        if (isCurrent && payload.strut_id === selectedStrutId) {
          setGalleryState({ status: 'ready', strutId: selectedStrutId, data: payload, error: null });
        }
      } catch (error) {
        if (error.name !== 'AbortError' && isCurrent) {
          setGalleryState({ status: 'error', strutId: selectedStrutId, data: null, error: error.message });
        }
      }
    }

    loadRoiEvidence();
    return () => {
      isCurrent = false;
      controller.abort();
    };
  }, [selectedStrutId, requestVersion]);

  if (selectedStrutId === null || selectedStrutId === undefined) {
    return (
      <section style={cardStyle}>
        <h3 style={headingStyle}>Local ROI Evidence</h3>
        <p style={mutedStyle}>Select a provisional candidate to generate local CT and mask views.</p>
      </section>
    );
  }

  if (galleryState.status === 'loading' || galleryState.strutId !== selectedStrutId) {
    return (
      <section style={cardStyle} aria-live="polite">
        <h3 style={headingStyle}>Local ROI Evidence</h3>
        <p style={mutedStyle}>Generating CT/mask overlays for strut #{selectedStrutId}…</p>
      </section>
    );
  }

  if (galleryState.status === 'error') {
    return (
      <section style={cardStyle} role="alert">
        <h3 style={headingStyle}>Local ROI Evidence</h3>
        <p style={{ color: '#ffb3b3' }}>{galleryState.error}</p>
        <button type="button" onClick={() => setRequestVersion((version) => version + 1)} style={retryStyle}>
          Retry local analysis
        </button>
      </section>
    );
  }

  const data = galleryState.data;
  if (!data) {
    return null;
  }

  const roi = data.roi ?? {};
  const warning = data.calibration_warning || FALLBACK_WARNING;

  return (
    <section style={cardStyle}>
      <h3 style={headingStyle}>Local ROI Evidence</h3>
      <p style={mutedStyle}>
        Raw CT is grayscale; red is the thresholded segmentation mask. These views are local evidence,
        not confirmation of a defect.
      </p>

      <div style={imageGridStyle}>
        {IMAGE_DETAILS.map((image) => {
          const relativeUrl = data.artifact_urls?.[image.key];
          if (!relativeUrl) return null;
          const expanded = { ...image, strutId: selectedStrutId, url: `${API_ORIGIN}${relativeUrl}` };
          return (
            <button
              key={image.key}
              type="button"
              onClick={() => setExpandedImage(expanded)}
              style={thumbnailButtonStyle}
              aria-label={`Expand ${image.label} ROI overlay for strut #${selectedStrutId}`}
            >
              <img src={expanded.url} alt={`${image.label} CT and mask overlay`} style={thumbnailImageStyle} />
              <span style={thumbnailLabelStyle}>{image.label}</span>
            </button>
          );
        })}
      </div>

      <div style={metadataStyle}>
        <div><span>ROI shape (ZYX)</span><strong>{formatCoordinates(roi.shape_zyx)}</strong></div>
        <div><span>Midpoint (ZYX)</span><strong>{formatCoordinates(roi.midpoint_zyx)}</strong></div>
        <div><span>Coordinates</span><strong>{roi.coordinate_convention || 'Unavailable'}</strong></div>
      </div>

      <p style={warningStyle}>{warning}</p>

      {expandedImage?.strutId === selectedStrutId && (
        <div role="dialog" aria-modal="true" aria-label={`${expandedImage.label} ROI overlay`} style={modalBackdropStyle}>
          <div style={modalStyle}>
            <div style={modalHeaderStyle}>
              <div>
                <strong>{expandedImage.label} local ROI</strong>
                <div style={mutedStyle}>{expandedImage.description}</div>
              </div>
              <button type="button" onClick={() => setExpandedImage(null)} style={closeStyle} aria-label="Close enlarged ROI image">
                ×
              </button>
            </div>
            <img src={expandedImage.url} alt={`${expandedImage.label} enlarged CT and mask overlay`} style={expandedImageStyle} />
          </div>
        </div>
      )}
    </section>
  );
}

const cardStyle = {
  backgroundColor: '#2a2a2a',
  borderRadius: '8px',
  padding: '15px',
};

const headingStyle = { marginTop: 0, marginBottom: '10px' };
const mutedStyle = { color: '#b8b8b8', marginTop: 0, lineHeight: 1.45 };

const imageGridStyle = {
  display: 'grid',
  gap: '8px',
  gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
};

const thumbnailButtonStyle = {
  background: '#161616',
  border: '1px solid #4b5563',
  borderRadius: '5px',
  color: '#d1d5db',
  cursor: 'pointer',
  minWidth: 0,
  overflow: 'hidden',
  padding: 0,
};

const thumbnailImageStyle = { display: 'block', height: '88px', objectFit: 'cover', width: '100%' };
const thumbnailLabelStyle = { display: 'block', fontSize: '0.75rem', fontWeight: 700, padding: '5px' };

const metadataStyle = {
  display: 'grid',
  fontSize: '0.8rem',
  gap: '6px',
  marginTop: '12px',
};

const warningStyle = {
  backgroundColor: '#42351f',
  borderLeft: '3px solid #ffbd59',
  color: '#ffe2a7',
  fontSize: '0.8rem',
  lineHeight: 1.35,
  marginBottom: 0,
  padding: '8px',
};

const retryStyle = {
  backgroundColor: '#244c49',
  border: '1px solid #62d5c5',
  borderRadius: '4px',
  color: '#d7fffb',
  cursor: 'pointer',
  padding: '8px 10px',
};

const modalBackdropStyle = {
  alignItems: 'center',
  backgroundColor: 'rgba(0, 0, 0, 0.78)',
  display: 'flex',
  inset: 0,
  justifyContent: 'center',
  padding: '24px',
  position: 'fixed',
  zIndex: 20,
};

const modalStyle = {
  backgroundColor: '#202020',
  border: '1px solid #4b5563',
  borderRadius: '8px',
  maxHeight: '90vh',
  maxWidth: 'min(900px, 95vw)',
  overflow: 'auto',
  padding: '16px',
};

const modalHeaderStyle = {
  alignItems: 'flex-start',
  display: 'flex',
  gap: '20px',
  justifyContent: 'space-between',
  marginBottom: '10px',
};

const closeStyle = {
  backgroundColor: 'transparent',
  border: 'none',
  color: 'white',
  cursor: 'pointer',
  fontSize: '1.8rem',
  lineHeight: 1,
};

const expandedImageStyle = { display: 'block', height: 'auto', maxWidth: '100%' };
