"use client";

import { useState, useEffect, RefObject } from "react";

interface MousePosition {
  x: number;
  y: number;
  relativeX: number;
  relativeY: number;
}

export function useMousePosition(ref?: RefObject<HTMLElement>): MousePosition {
  const [position, setPosition] = useState<MousePosition>({
    x: 0,
    y: 0,
    relativeX: 0.5,
    relativeY: 0.5,
  });

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (ref?.current) {
        const rect = ref.current.getBoundingClientRect();
        setPosition({
          x: event.clientX,
          y: event.clientY,
          relativeX: (event.clientX - rect.left) / rect.width,
          relativeY: (event.clientY - rect.top) / rect.height,
        });
      } else {
        setPosition({
          x: event.clientX,
          y: event.clientY,
          relativeX: event.clientX / window.innerWidth,
          relativeY: event.clientY / window.innerHeight,
        });
      }
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [ref]);

  return position;
}
