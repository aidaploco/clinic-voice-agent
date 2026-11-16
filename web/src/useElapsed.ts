import { useEffect, useState } from "react";

/** Seconds since `running` became true, as m:ss. Resets when it turns false. */
export function useElapsed(running: boolean): string {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) return;
    const began = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - began) / 1000)), 500);
    return () => {
      clearInterval(timer);
      setSeconds(0);
    };
  }, [running]);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
