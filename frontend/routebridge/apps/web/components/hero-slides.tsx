'use client';

// The moving photo slideshow: the landing page hero, and the photo banners on the Admin console, the shop portal and the
// rider app all use this one, so they look exactly alike. Styles: .lp-hero-slides / .lp-hero-slide in app/globals.css (the box
// around it needs position:relative, overflow:hidden and isolation:isolate; .photo-hero gives that plus the navy wash).
import { useEffect, useState, type CSSProperties } from 'react';

// The hero's photos: each one fades in and zooms slowly, then the next takes over. `small` is a lighter copy for phones;
// `position` / `smallPosition` keep the important part (the people) in view when the photo is cropped on wide screens / phones.
// Add a photo here to add a slide.
const HERO_PHOTOS: { src: string; small: string; position: string; smallPosition: string }[] = [
  { src: '/routebridge-bg.jpg', small: '/routebridge-bg-sm.jpg', position: '72% 45%', smallPosition: '78% center' },
  { src: '/routebridge-hero-road.jpg', small: '/routebridge-hero-road-sm.jpg', position: 'center 8%', smallPosition: '45% center' },
  { src: '/routebridge-hero-handover.jpg', small: '/routebridge-hero-handover-sm.jpg', position: 'center 30%', smallPosition: '62% center' },
];
const SLIDE_SECONDS = 7;

export function HeroSlides() {
  // `leaving` keeps the previous photo's zoom running while it fades out, so it never snaps back mid-fade
  const [{ active, leaving }, setSlides] = useState({ active: 0, leaving: -1 });
  useEffect(() => {
    if (HERO_PHOTOS.length < 2) return;
    const timer = setInterval(() => setSlides(({ active: current }) => ({ active: (current + 1) % HERO_PHOTOS.length, leaving: current })), SLIDE_SECONDS * 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="lp-hero-slides" aria-hidden="true">
      {HERO_PHOTOS.map((photo, index) => (
        <span
          key={photo.src}
          className={`lp-hero-slide${index === active ? ' is-active' : index === leaving ? ' is-leaving' : ''}${HERO_PHOTOS.length < 2 ? ' is-only' : ''}`}
          style={{ '--photo': `url('${photo.src}')`, '--photo-sm': `url('${photo.small}')`, '--photo-pos': photo.position, '--photo-pos-sm': photo.smallPosition } as CSSProperties}
        />
      ))}
    </div>
  );
}
