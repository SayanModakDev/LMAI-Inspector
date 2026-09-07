import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const SystemHealthContext = createContext(null);

export function SystemHealthProvider({ children }) {
  const [healthState, setHealthState] = useState('UNKNOWN'); // 'ONLINE' | 'DEGRADED' | 'OFFLINE' | 'UNKNOWN'
  const [healthData, setHealthData] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);
  const [isChecking, setIsChecking] = useState(false);

  const checkHealth = useCallback(async () => {
    setIsChecking(true);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 6000);

    try {
      const res = await fetch('/health', {
        signal: controller.signal,
        headers: { 'Accept': 'application/json' }
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        setHealthData(data);
        setLastChecked(new Date());
        
        // Check reported status
        const status = (data.status || '').toLowerCase();
        if (status === 'running' || status === 'healthy' || status === 'ok') {
          setHealthState('ONLINE');
        } else if (status === 'degraded' || status === 'warning') {
          setHealthState('DEGRADED');
        } else {
          setHealthState('ONLINE');
        }
      } else {
        setHealthData({ error: `HTTP ${res.status}` });
        setHealthState('DEGRADED');
        setLastChecked(new Date());
      }
    } catch (err) {
      clearTimeout(timeoutId);
      setHealthData(null);
      setHealthState('OFFLINE');
      setLastChecked(new Date());
    } finally {
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
      refreshHealth: () => {},
    };
  }
  return context;
}
