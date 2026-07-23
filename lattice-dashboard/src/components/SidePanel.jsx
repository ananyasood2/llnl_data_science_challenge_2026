// Add setFocusedDefectId to the props
export default function SidePanel({ defectsData, setFocusedDefectId }) {
  if (!defectsData) return <div style={{ padding: '20px' }}>Loading Diagnostics...</div>;

  return (
    <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <h2>Lattice Diagnostics</h2>
      
      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px' }}>
        <h3>Defect Summary</h3>
        <p><strong>Status:</strong> {defectsData.status}</p>
        <p><strong>Total Expected Struts:</strong> {defectsData.summary.total_expected_struts}</p>
        <p><strong>Missing Struts:</strong> <span style={{ color: '#ff4444', fontWeight: 'bold' }}>{defectsData.summary.missing_defects_count}</span></p>
        <p><strong>Defect Percentage:</strong> {defectsData.summary.defect_percentage}</p>
      </div>

      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px', flexGrow: 1, overflowY: 'auto', maxHeight: '400px' }}>
        <h3>Missing Strut IDs</h3>
        <ul style={{ listStyleType: 'none', padding: 0 }}>
          {defectsData.defective_strut_ids.map((id) => (
            <li key={id} style={{ padding: '10px 0', borderBottom: '1px solid #444' }}>
              {/* NEW: Add the onClick handler here */}
              <button 
                onClick={() => setFocusedDefectId(id)}
                style={{ cursor: 'pointer', background: 'none', color: '#646cff', border: 'none', fontWeight: 'bold' }}
              >
                Focus Defect #{id}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px' }}>
        <h3>Agent Co-Pilot</h3>
        <input 
          type="text" 
          placeholder="Ask about the defects..." 
          style={{ width: '100%', padding: '10px', borderRadius: '4px', border: 'none' }}
        />
      </div>
    </div>
  );
}