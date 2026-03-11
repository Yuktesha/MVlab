import { Composition, staticFile } from 'remotion';
import { Slideshow } from './components/Slideshow';
import React from 'react';

export const RemotionRoot: React.FC = () => {
    return (
        <>
            <Composition
                id="Slideshow"
                component={Slideshow}
                durationInFrames={300} // Default fallback
                fps={30}
                width={1920}
                height={1080}
                defaultProps={{
                    title: "My Video",
                    images: [],
                    themeConfig: {
                        duration: 4,
                        transition: 1
                    }
                }}
                calculateMetadata={({ props }) => {
                    const fps = 30;
                    const imageDuration = props.themeConfig?.duration || 4;
                    const transitionDuration = props.themeConfig?.transition || 1;

                    // Default to 1080p if not specified (legacy behavior)
                    const width = props.themeConfig?.width || 1920;
                    const height = props.themeConfig?.height || 1080;

                    if (!props.images || props.images.length === 0) {
                        return { durationInFrames: 300, width, height };
                    }

                    // Logic: Total = (N * Duration) - ((N-1) * Overlap)
                    const count = props.images.length;
                    const totalSeconds = (count * imageDuration) - ((count - 1) * transitionDuration);

                    return {
                        durationInFrames: Math.ceil(totalSeconds * fps),
                        width,
                        height
                    };
                }}
            />
            {/* Same updates for other compositions roughly */}
            <Composition
                id="DynamicOverlay"
                component={Slideshow}
                durationInFrames={300}
                fps={30}
                width={1920}
                height={1080}
                defaultProps={{
                    title: "Dynamic Overlay",
                    images: [],
                    themeConfig: {}
                }}
            />
            <Composition
                id="AutoEdit"
                component={Slideshow}
                durationInFrames={300}
                fps={30}
                width={1920}
                height={1080}
                defaultProps={{
                    title: "Auto Edit",
                    images: [],
                    themeConfig: {}
                }}
            />
        </>
    );
};
