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


    // Find navigation controls

    const filters = document.querySelector("[data-filters]");

    const filtersToggle = filters?.querySelector(
        "[data-filters-toggle]"
    );

    const filtersPanel = filters?.querySelector(
        "[data-filters-panel]"
    );

    const filtersForm = filters?.querySelector(
        "[data-filters-form]"
    );

    const filterSearch = filters?.querySelector(
        "[data-filter-search]"
    );

    const navigationSearch = document.querySelector(
        "#navigation-search"
    );

    const accountMenu = document.querySelector(
        "[data-account-menu]"
    );

    const accountToggle = accountMenu?.querySelector(
        "[data-account-menu-toggle]"
    );

    const accountPanel = accountMenu?.querySelector(
        "[data-account-menu-panel]"
    );


    // Close the filters panel

    const closeFilters = () => {
        if (!filtersPanel || !filtersToggle) {
            return;
        }

        filtersPanel.hidden = true;

        filtersToggle.setAttribute(
            "aria-expanded",
            "false"
        );

        filtersToggle.setAttribute(
            "aria-label",
            "Open event filters"
        );
    };


    // Close the account menu

    const closeAccountMenu = () => {
        if (!accountPanel || !accountToggle) {
            return;
        }

        accountPanel.hidden = true;

        accountToggle.setAttribute(
            "aria-expanded",
            "false"
        );

        accountToggle.setAttribute(
            "aria-label",
            "Open account menu"
        );
    };


    // Open the filters panel

    const openFilters = () => {
        if (!filtersPanel || !filtersToggle) {
            return;
        }

        closeAccountMenu();

        filtersPanel.hidden = false;

        filtersToggle.setAttribute(
            "aria-expanded",
            "true"
        );

        filtersToggle.setAttribute(
            "aria-label",
            "Close event filters"
        );

        if (filterSearch && navigationSearch) {
            filterSearch.value = navigationSearch.value;
        }
    };


    // Open the account menu

    const openAccountMenu = () => {
        if (!accountPanel || !accountToggle) {
            return;
        }

        closeFilters();

        accountPanel.hidden = false;

        accountToggle.setAttribute(
            "aria-expanded",
            "true"
        );

        accountToggle.setAttribute(
            "aria-label",
            "Close account menu"
        );
    };


    // Toggle the navigation filters

    if (filtersToggle && filtersPanel) {
        filtersToggle.addEventListener(
            "click",
            (event) => {
                event.stopPropagation();

                if (filtersPanel.hidden) {
                    openFilters();
                } else {
                    closeFilters();
                }
            }
        );

        filtersPanel.addEventListener(
            "click",
            (event) => {
                event.stopPropagation();
            }
        );
    }


    // Keep the search value when filters are applied

    if (filtersForm) {
        filtersForm.addEventListener(
            "submit",
            () => {
                if (filterSearch && navigationSearch) {
                    filterSearch.value =
                        navigationSearch.value;
                }
            }
        );
    }


    // Toggle the account menu

    if (accountToggle && accountPanel) {
        accountToggle.addEventListener(
            "click",
            (event) => {
                event.stopPropagation();

                if (accountPanel.hidden) {
                    openAccountMenu();
                } else {
                    closeAccountMenu();
                }
            }
        );

        accountPanel.addEventListener(
            "click",
            (event) => {
                event.stopPropagation();
            }
        );
    }


    // Close open navigation panels when clicking elsewhere

    document.addEventListener(
        "click",
        (event) => {
            if (
                filters &&
                filtersPanel &&
                !filtersPanel.hidden &&
                !filters.contains(event.target)
            ) {
                closeFilters();
            }

            if (
                accountMenu &&
                accountPanel &&
                !accountPanel.hidden &&
                !accountMenu.contains(event.target)
            ) {
                closeAccountMenu();
            }
        }
    );


    // Close open navigation panels with the Escape key

    document.addEventListener(
        "keydown",
        (event) => {
            if (event.key !== "Escape") {
                return;
            }

            if (
                filtersPanel &&
                !filtersPanel.hidden
            ) {
                closeFilters();

                filtersToggle?.focus();

                return;
            }

            if (
                accountPanel &&
                !accountPanel.hidden
            ) {
                closeAccountMenu();

                accountToggle?.focus();
            }
        }
    );


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

            const trackStyles =
                window.getComputedStyle(track);

            const gap =
                Number.parseFloat(
                    trackStyles.columnGap
                ) || 0;

            return (
                firstSlide
                    .getBoundingClientRect()
                    .width + gap
            );
        };


        // Update the visible carousel controls

        const updateControls = () => {
            const maximumScroll =
                viewport.scrollWidth -
                viewport.clientWidth;

            const edgeTolerance = 4;

            const canScroll =
                maximumScroll > edgeTolerance;

            previous.hidden = !canScroll;
            next.hidden = !canScroll;

            previous.disabled =
                !canScroll ||
                viewport.scrollLeft <=
                    edgeTolerance;

            next.disabled =
                !canScroll ||
                viewport.scrollLeft >=
                    maximumScroll -
                        edgeTolerance;
        };


        // Move the carousel by exactly one card

        const moveCarousel = (direction) => {
            viewport.scrollBy({
                left:
                    direction *
                    getStepSize(),

                behavior:
                    reduceMotion
                        ? "auto"
                        : "smooth",
            });
        };

        previous.addEventListener(
            "click",
            () => {
                moveCarousel(-1);
            }
        );

        next.addEventListener(
            "click",
            () => {
                moveCarousel(1);
            }
        );

        viewport.addEventListener(
            "scroll",
            updateControls,
            {
                passive: true,
            }
        );


        // Allow keyboard carousel navigation

        viewport.addEventListener(
            "keydown",
            (event) => {
                if (event.key === "ArrowLeft") {
                    event.preventDefault();

                    moveCarousel(-1);
                }

                if (event.key === "ArrowRight") {
                    event.preventDefault();

                    moveCarousel(1);
                }
            }
        );


        // Measure the carousel after layout changes

        const measureCarousel = () => {
            updateControls();

            window.requestAnimationFrame(
                updateControls
            );
        };

        if (window.ResizeObserver) {
            const resizeObserver =
                new ResizeObserver(
                    measureCarousel
                );

            resizeObserver.observe(
                viewport
            );

            resizeObserver.observe(
                track
            );
        } else {
            window.addEventListener(
                "resize",
                measureCarousel
            );
        }

        viewport
            .querySelectorAll("img")
            .forEach((image) => {
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
            document.fonts.ready.then(
                measureCarousel
            );
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