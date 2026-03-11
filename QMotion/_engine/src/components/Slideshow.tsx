import { AbsoluteFill, Img, interpolate, Sequence, useCurrentFrame, useVideoConfig, staticFile } from 'remotion';
import React from 'react';
import { TitleOverlay } from './TitleOverlay';

const KenBurnsImage: React.FC<{ src: string; index: number; fitMode?: string }> = ({ src, index, fitMode = 'cover' }) => {
    const frame = useCurrentFrame();

    // Simple subtle zoom
    const scale = interpolate(frame, [0, 100], [1.05, 1.15], { extrapolateRight: 'clamp' });

    // Slow pan (alternating direction)
    const xDir = index % 2 === 0 ? -1 : 1;
    const translateX = interpolate(frame, [0, 100], [0, 20 * xDir], { extrapolateRight: 'clamp' });

    const isBlurMode = fitMode === 'contain-blur';
    const actualFit = (isBlurMode ? 'contain' : fitMode) as any;

    return (
        <AbsoluteFill style={{ overflow: 'hidden' }}>
            {isBlurMode && (
                <AbsoluteFill>
                    <Img
                        src={staticFile(src)}
                        style={{
                            width: '100%',
                            height: '100%',
                            objectFit: 'cover',
                            filter: 'blur(40px)',
                            opacity: 0.8,
                            transform: 'scale(1.2)'
                        }}
                    />
                </AbsoluteFill>
            )}
            <Img
                src={staticFile(src)}
                style={{
                    width: '100%',
                    height: '100%',
                    objectFit: actualFit,
                    transform: `scale(${scale}) translateX(${translateX}px)`
                }}
            />
        </AbsoluteFill>
    );
};

const FadingImage: React.FC<{
    src: string;
    index: number;
    duration: number;
    transition: number;
    fitMode?: string;
}> = ({ src, index, duration, transition, fitMode }) => {
    const frame = useCurrentFrame();

    // Fade in/out logic
    const fadeIn = interpolate(frame, [0, transition], [0, 1], { extrapolateRight: 'clamp' });
    const fadeOut = interpolate(frame, [duration - transition, duration], [1, 0], { extrapolateLeft: 'clamp' });
    const opacity = Math.min(fadeIn, fadeOut);

    return (
        <AbsoluteFill style={{ opacity }}>
            <KenBurnsImage src={src} index={index} fitMode={fitMode} />
        </AbsoluteFill>
    );
};

export const Slideshow: React.FC<{
    title: string;
    images: string[];
    themeConfig: any;
}> = ({ title, images, themeConfig }) => {
    const { fps } = useVideoConfig();

    const durationSeconds = themeConfig?.duration || 4;
    const transitionSeconds = themeConfig?.transition || 1;
    const fitMode = themeConfig?.fitMode || 'cover';

    const imageDuration = Math.ceil(fps * durationSeconds);
    const transitionDuration = Math.ceil(fps * transitionSeconds);

    return (
        <AbsoluteFill style={{ backgroundColor: 'black' }}>
            {images.map((img, i) => {
                const startFrame = i * (imageDuration - transitionDuration);

                return (
                    <Sequence
                        key={i}
                        from={startFrame}
                        durationInFrames={imageDuration}
                        layout="none"
                    >
                        <FadingImage
                            src={img}
                            index={i}
                            duration={imageDuration}
                            transition={transitionDuration}
                            fitMode={fitMode}
                        />
                    </Sequence>
                );
            })}
            <TitleOverlay title={title} />
        </AbsoluteFill>
    );
};
