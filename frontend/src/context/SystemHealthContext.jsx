import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { resolveBackendUrl } from '../services/api';

const SystemHealthContext = createContext(null);

export function SystemHealthProvider({ children }) {
  const [healthState, setHealthState] = useState('UNKNOWN'); // 'ONLINE' | 'DEGRADED' | 'OFFLINE' | 'UNKNOWN'
  const [healthData, setHealthData] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);
  const [isChecking, setIsChecking] = useState(false);
  const [analysisInProgress, setAnalysisInProgress] = useState(false);
  const consecutiveFailuresRef = useRef(0);
  const checkInFlightRef = useRef(false);

  const checkHealth = useCallback(async () => {
    if (checkInFlightRef.current) return;
    checkInFlightRef.current = true;
    setIsChecking(true);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 6000);

    try {
      const healthUrl = resolveBackendUrl('/health');
      const res = await fetch(healthUrl, {
        signal: controller.signal,
        headers: { 'Accept': 'application/json' }
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        consecutiveFailuresRef.current = 0;
        setHealthData(data);
        setLastChecked(new Date());
        
        // Check reported status from backend
        const status = (data.status || '').toLowerCase();
        if (status === 'running' || status === 'healthy' || status === 'ok') {
          setHealthState('ONLINE');
        } else if (status === 'degraded' || status === 'warning') {
          setHealthState('DEGRADED');
        } else {
          setHealthState('UNKNOWN');
        }
      } else {
        consecutiveFailuresRef.current = 0;
        setHealthData({ error: `HTTP ${res.status}` });
        setHealthState('DEGRADED');
        setLastChecked(new Date());
      }
    } catch (err) {
      consecutiveFailuresRef.current += 1;
      setHealthData({
        error: err.name === 'AbortError' ? 'Health check timed out' : 'Health check failed',
      });
      setHealthState(consecutiveFailuresRef.current >= 2 ? 'OFFLINE' : 'DEGRADED');
      setLastChecked(new Date());
    } finally {
      clearTimeout(timeoutId);
      checkInFlightRef.current = false;
      setIsChecking(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    // Re-check periodically every 45 seconds
    const interval = setInterval(checkHealth, 45000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  return (
    <SystemHealthContext.Provider
      value={{
        healthState,
        healthData,
        lastChecked,
        isChecking,
        analysisInProgress,
        setAnalysisInProgress,
        refreshHealth: checkHealth,
      }}
    >
      {children}
    </SystemHealthContext.Provider>
  );
}

export function useSystemHealth() {
  const context = useContext(SystemHealthContext);
  if (!context) {
    return {
      healthState: 'UNKNOWN',
      healthData: null,
      lastChecked: null,
      isChecking: false,
      analysisInProgress: false,
      setAnalysisInProgress: () => {},
      refreshHealth: () => {},
    };
  }
  return context;
}
