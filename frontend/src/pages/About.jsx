import BrandLogo from '../components/BrandLogo';

const About = () => {
  return (
    <div className="max-w-3xl mx-auto">
      <div className="card">
        <div className="card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>About LMAI Inspector</span>
          <BrandLogo variant="horizontal" height={28} alt="LMAI Inspector" />
        </div>
        <div className="card-body">
          <p className="mb-4">
            This application is an inspection support tool designed to assist Legal Metrology 
            inspectors in verifying packaged commodity declarations.
          </p>
          
          <h3 className="mt-3 mb-2">How it works</h3>
          <ol style={{ paddingLeft: '1.5rem', marginBottom: '1.5rem' }}>
            <li className="mb-2"><strong>Scan:</strong> Upload an image of a packaged commodity label.</li>
            <li className="mb-2"><strong>Extract:</strong> PaddleOCR extracts text, and the system identifies declarations (MRP, Declared Net Quantity, Dates).</li>
            <li className="mb-2"><strong>Classify:</strong> The product is automatically classified into categories (e.g., FOOD, COSMETIC).</li>
            <li className="mb-2"><strong>Evaluate:</strong> A flexible rules engine validates the extracted declarations against the Legal Metrology (Packaged Commodities) Rules, 2011.</li>
            <li><strong>Report:</strong> The user can review extracted values, re-evaluate, and generate an inspection report PDF.</li>
          </ol>
          
          <div className="warning-banner" style={{ marginTop: '2rem' }}>
            <strong>Statutory Notice:</strong> This system is an inspection screening tool. Inspection outputs are recommendations to assist human verification and do not constitute legal certificates or statutory enforcement orders. Final regulatory determinations must be made by authorized personnel in accordance with the Legal Metrology (Packaged Commodities) Rules, 2011.
          </div>
        </div>
      </div>
    </div>
  );
};

export default About;
