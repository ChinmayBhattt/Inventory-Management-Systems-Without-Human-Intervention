"use client";

import React, { useEffect, useRef, useState } from "react";

interface AsciiFlameProps {
  mode?: "icon" | "compact" | "hero" | "banner";
  isExploding?: boolean;
  className?: string;
}

// Multi-frame ASCII flame animations
const FLAME_FRAMES_ICON = [
  [" ( ", " )\\", "(( )", " || "],
  [" ) ", "/( ", "( ))", " || "],
  ["( )", " (\\", "(( )", " || "],
  [" ) ", "/ )", " ( )", " || "],
];

const FLAME_FRAMES_COMPACT = [
  [
    "   (   ",
    "  ) \\  ",
    " ( ( ) ",
    "  ) )\\ ",
    " (____)",
  ],
  [
    "   )   ",
    "  / (  ",
    " ( ) ) ",
    " /(( ) ",
    " (____)",
  ],
  [
    "  ( )  ",
    "  ) )  ",
    " (( ( )",
    "  ) )\\ ",
    " (____)",
  ],
  [
    "   (   ",
    "  /( ) ",
    " ( ) ( ",
    " / ) ) ",
    " (____)",
  ],
];

const FLAME_FRAMES_HERO = [
  [
    "       .---.       ",
    "      /     \\      ",
    "     (( .-. ))     ",
    "    (( (   ) ))    ",
    "     )) ' ' ((     ",
    "    ((   *   ))    ",
    "     '-------'     ",
    "   * AUTO-STOCK *  ",
  ],
  [
    "       .---.       ",
    "      /  ^  \\      ",
    "     (( / \\ ))     ",
    "    (( ( * ) ))    ",
    "     ))  .  ((     ",
    "    ((  ***  ))    ",
    "     '-------'     ",
    "   * AUTO-STOCK *  ",
  ],
  [
    "       .---.       ",
    "      /  .  \\      ",
    "     ((  |  ))     ",
    "    (( ( . ) ))    ",
    "     )) * * ((     ",
    "    ((  ***  ))    ",
    "     '-------'     ",
    "   * AUTO-STOCK *  ",
  ],
  [
    "       .---.       ",
    "      /  *  \\      ",
    "     (( ' ' ))     ",
    "    (( ( | ) ))    ",
    "     ))  *  ((     ",
    "    (( * * * ))    ",
    "     '-------'     ",
    "   * AUTO-STOCK *  ",
  ],
];

const EXPLOSION_FRAMES = [
  [
    "      *  .  *      ",
    "    .  \\ | /  .    ",
    "   -- ( *** ) --   ",
    "    '  / | \\  '    ",
    "      *  '  *      ",
  ],
  [
    "    *   .   *   .  ",
    "   .  \\  |  /  .   ",
    "  -- (  ***  ) --  ",
    "   '  /  |  \\  '   ",
    "    .   *   .   *  ",
  ],
  [
    "  .   *       *   .",
    "    .   \\   /   .  ",
    "  ---  ( *** )  ---",
    "    '   /   \\   '  ",
    "  *   .       .   *",
  ],
];

export default function AsciiFlame({
  mode = "compact",
  isExploding = false,
  className = "",
}: AsciiFlameProps) {
  const [frameIndex, setFrameIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const isVisibleRef = useRef(true);

  const frames = isExploding
    ? EXPLOSION_FRAMES
    : mode === "hero" || mode === "banner"
    ? FLAME_FRAMES_HERO
    : mode === "icon"
    ? FLAME_FRAMES_ICON
    : FLAME_FRAMES_COMPACT;

  const frameIntervalMs = isExploding ? 40 : 85;

  useEffect(() => {
    // Check prefers-reduced-motion
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mediaQuery.matches) {
      return;
    }

    // IntersectionObserver to pause when off-screen
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          isVisibleRef.current = entry.isIntersecting;
        });
      },
      { threshold: 0.1 }
    );

    if (containerRef.current) {
      observer.observe(containerRef.current);
    }

    const interval = setInterval(() => {
      if (isVisibleRef.current) {
        setFrameIndex((prev) => (prev + 1) % frames.length);
      }
    }, frameIntervalMs);

    return () => {
      clearInterval(interval);
      observer.disconnect();
    };
  }, [frames.length, frameIntervalMs]);

  const activeLines = frames[frameIndex % frames.length];

  return (
    <div
      ref={containerRef}
      className={`select-none font-mono tracking-tighter leading-none inline-block text-heat ${className}`}
      aria-hidden="true"
      style={{
        textShadow: "0 0 10px rgba(250, 93, 25, 0.45)",
      }}
    >
      <pre className="font-mono text-[11px] sm:text-xs leading-[1.1] m-0 p-0 text-center text-heat font-bold">
        {activeLines.join("\n")}
      </pre>
    </div>
  );
}

