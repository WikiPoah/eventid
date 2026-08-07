document.documentElement.classList.add("js");

document.addEventListener("DOMContentLoaded", () => {
    const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;


    // Animate staggered content when it enters the viewport

    document.querySelectorAll(".stagger-grid").forEach((grid) => {
        const items = grid.querySelectorAll(":scope > .stagger-item");

        items.forEach((item, index) => {
            item.style.setProperty(
                "--stagger-index",
                Math.min(index, 12)
            );
        });

        if (reduceMotion || !window.IntersectionObserver) {
            grid.classList.add("is-visible");

            return;
        }

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("is-visible");

                        observer.unobserve(entry.target);
                    }
                });
            },
            {
                threshold: 0.08,
            }
        );

        observer.observe(grid);
    });


    // Handle the account dropdown menu

    document.querySelectorAll("[data-account-menu]").forEach((menu) => {
        const toggle = menu.querySelector(
            "[data-account-menu-toggle]"
        );

        const panel = menu.querySelector(
            "[data-account-menu-panel]"
        );

        if (!toggle || !panel) {
            return;
        }

        const openMenu = () => {
            panel.hidden = false;

            toggle.setAttribute("aria-expanded", "true");
            toggle.setAttribute("aria-label", "Close account menu");
        };

        const closeMenu = () => {
            panel.hidden = true;

            toggle.setAttribute("aria-expanded", "false");
            toggle.setAttribute("aria-label", "Open account menu");
        };

        toggle.addEventListener("click", (event) => {
            event.stopPropagation();

            if (panel.hidden) {
                openMenu();
            } else {
                closeMenu();
            }
        });

        panel.addEventListener("click", (event) => {
            event.stopPropagation();
        });

        document.addEventListener("click", (event) => {
            if (
                !panel.hidden &&
                !menu.contains(event.target)
            ) {
                closeMenu();
            }
        });

        document.addEventListener("keydown", (event) => {
            if (
                event.key === "Escape" &&
                !panel.hidden
            ) {
                closeMenu();

                toggle.focus();
            }
        });
    });


    // Initialise each homepage event carousel independently

    document.querySelectorAll("[data-carousel]").forEach((carousel) => {
        const viewport = carousel.querySelector(
            "[data-carousel-viewport]"
        );

        const track = carousel.querySelector(
            "[data-carousel-track]"
        );

        const previous = carousel.querySelector(
            "[data-carousel-previous]"
        );

        const next = carousel.querySelector(
            "[data-carousel-next]"
        );

        if (!viewport || !track || !previous || !next) {
            return;
        }

        const slides = Array.from(
            track.querySelectorAll(".carousel-slide")
        );


        // Calculate the distance of one card and one gap

        const getStepSize = () => {
            const firstSlide = slides[0];

            if (!firstSlide) {
                return viewport.clientWidth;
            }

            const trackStyles = window.getComputedStyle(track);

            const gap =
                Number.parseFloat(trackStyles.columnGap) || 0;

            return firstSlide.getBoundingClientRect().width + gap;
        };


        // Update the visible carousel controls

        const updateControls = () => {
            const maximumScroll =
                viewport.scrollWidth - viewport.clientWidth;

            const edgeTolerance = 4;

            const canScroll =
                maximumScroll > edgeTolerance;

            previous.hidden = !canScroll;
            next.hidden = !canScroll;

            previous.disabled =
                !canScroll ||
                viewport.scrollLeft <= edgeTolerance;

            next.disabled =
                !canScroll ||
                viewport.scrollLeft >=
                    maximumScroll - edgeTolerance;
        };


        // Move the carousel by exactly one card

        const moveCarousel = (direction) => {
            viewport.scrollBy({
                left: direction * getStepSize(),
                behavior: reduceMotion ? "auto" : "smooth",
            });
        };

        previous.addEventListener("click", () => {
            moveCarousel(-1);
        });

        next.addEventListener("click", () => {
            moveCarousel(1);
        });

        viewport.addEventListener(
            "scroll",
            updateControls,
            {
                passive: true,
            }
        );


        // Allow keyboard carousel navigation

        viewport.addEventListener("keydown", (event) => {
            if (event.key === "ArrowLeft") {
                event.preventDefault();

                moveCarousel(-1);
            }

            if (event.key === "ArrowRight") {
                event.preventDefault();

                moveCarousel(1);
            }
        });


        // Measure the carousel after layout changes

        const measureCarousel = () => {
            updateControls();

            window.requestAnimationFrame(updateControls);
        };

        if (window.ResizeObserver) {
            const resizeObserver = new ResizeObserver(
                measureCarousel
            );

            resizeObserver.observe(viewport);
            resizeObserver.observe(track);
        } else {
            window.addEventListener(
                "resize",
                measureCarousel
            );
        }

        viewport.querySelectorAll("img").forEach((image) => {
            if (!image.complete) {
                image.addEventListener(
                    "load",
                    measureCarousel,
                    {
                        once: true,
                    }
                );
            }
        });

        if (document.fonts?.ready) {
            document.fonts.ready.then(measureCarousel);
        }

        window.addEventListener(
            "load",
            measureCarousel,
            {
                once: true,
            }
        );

        measureCarousel();
    });
});