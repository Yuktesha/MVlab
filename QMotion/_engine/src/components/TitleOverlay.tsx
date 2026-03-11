import React from 'react';
import { AbsoluteFill, useVideoConfig, useCurrentFrame, interpolate } from 'remotion';

export const TitleOverlay: React.FC<{ title: string }> = ({ title }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig(); // use width/height if needed, but not unused

    // Simple fade in/out
    // Show for first 4 seconds (approx 120 frames at 30fps)
    const duration = 120;

    const opacity = interpolate(
        frame,
        [0, 20, duration - 20, duration],
        [0, 1, 1, 0],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
    );

    const scale = interpolate(frame, [0, duration], [0.9, 1.05]);

    // If frame > duration, we can hide it effectively (opacity 0)
    if (frame > duration) return null;

    return (
        <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', zIndex: 100, opacity }}>
            <h1 style={{
                fontFamily: 'Segoe UI, sans-serif',
                fontSize: 100,
                color: 'white',
                textShadow: '0 4px 10px rgba(0,0,0,0.5)',
                transform: `scale(${scale})`,
                textAlign: 'center',
                maxWidth: '80%',
                margin: 0
            }}>
                {title}
            </h1>
        </AbsoluteFill>
    );
};
