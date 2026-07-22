export default function SidePanel() {
  return (
    <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <h2>Lattice Diagnostics</h2>
      
      {/* Stats Card */}
      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px' }}>
        <h3>Defect Summary</h3>
        <p><strong>Total Expected Struts:</strong> --</p>
        <p><strong>Missing Struts:</strong> --</p>
        <p><strong>Defect Percentage:</strong> --%</p>
      </div>

      {/* List of Defects */}
      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px', flexGrow: 1 }}>
        <h3>Missing Strut Coordinates</h3>
        <ul style={{ listStyleType: 'none', padding: 0 }}>
          <li style={{ padding: '10px 0', borderBottom: '1px solid #444' }}>
            <button style={{ cursor: 'pointer', background: 'none', color: '#646cff', border: 'none' }}>
              Focus Defect #1
            </button>
          </li>
          <li style={{ padding: '10px 0', borderBottom: '1px solid #444' }}>
            <button style={{ cursor: 'pointer', background: 'none', color: '#646cff', border: 'none' }}>
              Focus Defect #2
            </button>
          </li>
        </ul>
      </div>

      {/* Agent Chat Placeholder */}
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