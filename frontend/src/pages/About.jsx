const About = () => {
  return (
    <div className="max-w-3xl mx-auto">
      <div className="card">
        <div className="card-header">About Legal Metrology AI System</div>
        <div className="card-body">
          <p className="mb-4">
            This application is an AI-assisted compliance checking system designed to support Legal Metrology 
            inspectors in verifying packaged commodity declarations.
          </p>
          
          <h3 className="mt-3 mb-2">How it works</h3>
          <ol style={{ paddingLeft: '1.5rem', marginBottom: '1.5rem' }}>
            <li className="mb-2"><strong>Scan:</strong> Upload an image of a packaged commodity label.</li>
            <li className="mb-2"><strong>Extract:</strong> PaddleOCR extracts text, and the system identifies declarations (MRP, Net Qty, Dates).</li>
            <li className="mb-2"><strong>Classify:</strong> The product is automatically classified into categories (e.g., FOOD, COSMETIC).</li>
            <li className="mb-2"><strong>Evaluate:</strong> A flexible rules engine validates the extracted declarations against Legal Metrology guidelines.</li>
            <li><strong>Report:</strong> The inspector can manually override incorrect extractions, re-evaluate, and generate a final PDF report.</li>
          </ol>
          
          <div className="warning-banner" style={{ marginTop: '2rem' }}>
            <strong>Note:</strong> The final determination of legal compliance rests with the human inspector. 
            This tool highlights potential non-compliances for further review.
          </div>
        </div>
      </div>
    </div>
  );
};

export default About;
