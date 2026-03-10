import { useState, useEffect } from "react";

export default function SplashScreen({ onDone }) {
  const [showButtons, setShowButtons] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowButtons(true), 1800);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="splash">
      <div className="splash-icon">
        <svg viewBox="0 0 80 72" fill="none" xmlns="http://www.w3.org/2000/svg" className="splash-cart">
          <rect x="10" y="20" width="52" height="30" rx="4" fill="#ffffff" stroke="#0b6e4f" strokeWidth="2.5"/>
          <polyline points="4,8 14,8 24,50 56,50 64,24 14,24" fill="none" stroke="#0b6e4f" strokeWidth="2.5" strokeLinejoin="round"/>
          <circle cx="28" cy="60" r="5" fill="#0b6e4f"/>
          <circle cx="52" cy="60" r="5" fill="#0b6e4f"/>
          <path d="M40 18 C40 18 32 26 32 32 C32 36.4 35.6 40 40 40 C44.4 40 48 36.4 48 32 C48 26 40 18 40 18Z" fill="#F59E0B" stroke="#d97706" strokeWidth="1.5"/>
          <circle cx="40" cy="32" r="3.5" fill="#ffffff"/>
        </svg>
        <p className="splash-title">Boston Food Mapping System</p>
        <p className="splash-sub">Mapping access across neighborhoods</p>
        {showButtons && (
          <div className="splash-lang">
            <button className="splash-lang-btn" onClick={() => onDone("en")}>English</button>
            <button className="splash-lang-btn" onClick={() => onDone("es")}>Español</button>
          </div>
        )}
      </div>
    </div>
  );
}