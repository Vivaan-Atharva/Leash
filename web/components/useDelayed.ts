"use client";
import { useEffect, useState } from "react";

/** Show a value only after a delay, so screen updates land when the packet arrives. */
export function useDelayed<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
