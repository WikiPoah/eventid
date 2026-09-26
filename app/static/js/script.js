document.documentElement.classList.add("js");

document.addEventListener("DOMContentLoaded", () => {
    const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;

    const scrollStorageKey = `eventid-scroll:${window.location.pathname}`;
    const savedScrollPosition = sessionStorage.getItem(scrollStorageKey);
    if (savedScrollPosition !== null) {
        sessionStorage.removeItem(scrollStorageKey);
        window.requestAnimationFrame(() => {
            window.scrollTo(0, Number(savedScrollPosition));
        });
    }

    // Connect server-side validation messages to their form controls.

    document.querySelectorAll(".field-error").forEach((message, index) => {
        const field = message.closest(".form-field");
        const control = field?.querySelector("input, select, textarea");
        if (!control) {
            return;
        }

        if (!message.id) {
            message.id = `field-error-${index + 1}`;
        }
        control.setAttribute("aria-invalid", "true");
        const describedBy = new Set(
            (control.getAttribute("aria-describedby") || "")
                .split(/\s+/)
                .filter(Boolean)
        );
        describedBy.add(message.id);
        control.setAttribute("aria-describedby", [...describedBy].join(" "));
    });

    const copyPrivateInviteButton = document.querySelector(
        "[data-copy-private-invite]"
    );
    const privateInviteInput = document.querySelector("[data-private-invite-link]");
    if (copyPrivateInviteButton && privateInviteInput) {
        copyPrivateInviteButton.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(privateInviteInput.value);
                copyPrivateInviteButton.textContent = "Copied";
                window.setTimeout(() => {
                    copyPrivateInviteButton.textContent = "Copy Link";
                }, 1800);
            } catch (_error) {
                privateInviteInput.select();
            }
        });
    }


    // Update private attendance decisions without reloading the event page.

    document.addEventListener("submit", async (event) => {
        const form = event.target.closest("[data-private-attendance-action]");
        if (!form) {
            return;
        }

        event.preventDefault();
        const row = form.closest("[data-private-attendee-row]");
        const actionsContainer = row?.querySelector(
            "[data-private-attendee-actions]"
        );
        const statusBadge = row?.querySelector("[data-private-attendee-status]");
        const submitButton = form.querySelector("button[type='submit']");
        const csrfToken = form.querySelector("[name='csrf_token']")?.value;
        const liveStatus = document.querySelector("[data-private-action-status]");

        if (!row || !actionsContainer || !statusBadge || !csrfToken) {
            form.submit();
            return;
        }

        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: { Accept: "application/json" },
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || "The action could not be completed.");
            }

            statusBadge.textContent = result.status_label;
            statusBadge.className =
                `badge private-status private-status-${result.status.toLowerCase()}`;

            actionsContainer.replaceChildren();
            result.actions.forEach((action) => {
                const nextForm = document.createElement("form");
                nextForm.method = "POST";
                nextForm.action = action.url;
                nextForm.dataset.privateAttendanceAction = "";

                const tokenInput = document.createElement("input");
                tokenInput.type = "hidden";
                tokenInput.name = "csrf_token";
                tokenInput.value = csrfToken;

                const button = document.createElement("button");
                button.type = "submit";
                button.className = `button ${action.class_name}`;
                button.textContent = action.label;

                nextForm.append(tokenInput, button);
                actionsContainer.append(nextForm);
            });

            Object.entries(result.counts).forEach(([status, count]) => {
                const counter = document.querySelector(
                    `[data-private-status-count="${status}"]`
                );
                if (counter) {
                    counter.textContent = count;
                }
            });

            if (liveStatus) {
                liveStatus.textContent = result.message;
                liveStatus.classList.remove("is-error");
            }
        } catch (error) {
            if (liveStatus) {
                liveStatus.textContent = error.message;
                liveStatus.classList.add("is-error");
            } else {
                form.submit();
            }
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
            }
        }
    });


    // Save favourites without reloading the page or changing scroll position.

    document.addEventListener("submit", async (event) => {
        const form = event.target.closest("[data-favourite-form]");

        if (!form) {
            return;
        }

        event.preventDefault();

        const button = form.querySelector(".favourite-button");
        const eventId = form.dataset.eventId;
        const eventTitle = form.dataset.eventTitle;

        if (!button || !eventId) {
            return;
        }

        button.disabled = true;

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: { Accept: "application/json" },
            });

            if (!response.ok) {
                throw new Error("Favourite request failed");
            }

            const result = await response.json();

            document
                .querySelectorAll(
                    `[data-favourite-form][data-event-id="${eventId}"] .favourite-button`
                )
                .forEach((matchingButton) => {
                    matchingButton.classList.toggle(
                        "is-favourite",
                        result.is_favourite
                    );
                    matchingButton.setAttribute(
                        "aria-label",
                        result.is_favourite
                            ? `Remove ${eventTitle} from favourites`
                            : `Add ${eventTitle} to favourites`
                    );
                    matchingButton.title = result.is_favourite
                        ? "Remove from favourites"
                        : "Add to favourites";
                });
        } catch (_error) {
            form.submit();
        } finally {
            button.disabled = false;
        }
    });


    // Restore position when a POST action redirects back to the same page.

    document.addEventListener("submit", (event) => {
        if (event.defaultPrevented) {
            return;
        }

        const form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        if ((form.method || "get").toLowerCase() === "post") {
            sessionStorage.setItem(scrollStorageKey, String(window.scrollY));
        }
    });


    // Preview a newly selected event image before the form is submitted.

    document.querySelectorAll("[data-image-input]").forEach((input) => {
        const field = input.closest(".form-field");
        const preview = field?.querySelector("[data-image-preview]");
        const editor = field?.querySelector("[data-image-crop-editor]");
        const horizontal = field?.querySelector("[data-image-position-x]");
        const vertical = field?.querySelector("[data-image-position-y]");
        const cropX = field?.querySelector("[name='image_crop_x']");
        const cropY = field?.querySelector("[name='image_crop_y']");

        if (!preview) {
            return;
        }

        let previewUrl;

        input.addEventListener("change", () => {
            if (previewUrl) {
                URL.revokeObjectURL(previewUrl);
            }

            const [file] = input.files;
            if (!file) {
                preview.hidden = true;
                if (editor) {
                    editor.hidden = true;
                }
                preview.removeAttribute("src");
                return;
            }

            previewUrl = URL.createObjectURL(file);
            preview.src = previewUrl;
            preview.hidden = false;
            if (editor) {
                editor.hidden = false;
            }
        });

        const updatePosition = () => {
            const x = Number(horizontal?.value || 50);
            const y = Number(vertical?.value || 50);
            preview.style.objectPosition = `${x}% ${y}%`;
            if (cropX) {
                cropX.value = String(x);
            }
            if (cropY) {
                cropY.value = String(y);
            }
        };
        horizontal?.addEventListener("input", updatePosition);
        vertical?.addEventListener("input", updatePosition);
        updatePosition();
    });


    // Share public event pages without navigating away from the current page.

    const shareStatus = document.querySelector("[data-share-status]");

    const copyEventUrl = async (url) => {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(url);
            return;
        }

        const temporaryInput = document.createElement("textarea");
        temporaryInput.value = url;
        temporaryInput.setAttribute("readonly", "");
        temporaryInput.style.position = "fixed";
        temporaryInput.style.opacity = "0";
        document.body.appendChild(temporaryInput);
        temporaryInput.select();
        document.execCommand("copy");
        temporaryInput.remove();
    };

    document.querySelectorAll("[data-copy-event-link]").forEach((button) => {
        button.addEventListener("click", async () => {
            try {
                await copyEventUrl(button.dataset.shareUrl);
                if (shareStatus) {
                    shareStatus.textContent = "Event link copied.";
                }
            } catch (_error) {
                if (shareStatus) {
                    shareStatus.textContent = "The event link could not be copied.";
                }
            }
        });
    });

    document.querySelectorAll("[data-share-event]").forEach((button) => {
        button.addEventListener("click", async () => {
            const shareData = {
                title: button.dataset.shareTitle,
                url: button.dataset.shareUrl,
            };

            try {
                if (navigator.share) {
                    await navigator.share(shareData);
                } else {
                    await copyEventUrl(shareData.url);
                    if (shareStatus) {
                        shareStatus.textContent = "Event link copied.";
                    }
                }
            } catch (error) {
                if (error.name !== "AbortError" && shareStatus) {
                    shareStatus.textContent = "The event could not be shared.";
                }
            }
        });
    });


    // Animate staggered content when it enters the viewport

    document.querySelectorAll(".stagger-grid").forEach((grid) => {
        const items = grid.querySelectorAll(":scope > .stagger-item");
        const revealGrid = () => grid.classList.add("is-visible");

        items.forEach((item, index) => {
            item.style.setProperty(
                "--stagger-index",
                Math.min(index, 12)
            );
        });

        if (reduceMotion || !window.IntersectionObserver) {
            revealGrid();

            return;
        }

        // Reveal content already on screen immediately. Some browsers delay
        // the first observer callback until a scroll or layout change.
        const gridBounds = grid.getBoundingClientRect();
        if (
            gridBounds.top <= window.innerHeight + 160 &&
            gridBounds.bottom >= -160
        ) {
            revealGrid();
            return;
        }

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        revealGrid();

                        observer.unobserve(entry.target);
                    }
                });
            },
            {
                threshold: 0.08,
                rootMargin: "0px 0px 160px 0px",
            }
        );

        observer.observe(grid);
    });

    // Pages restored from browser history can skip a fresh observer callback.
    window.addEventListener("pageshow", () => {
        document.querySelectorAll(".stagger-grid").forEach((grid) => {
            const bounds = grid.getBoundingClientRect();
            if (bounds.top <= window.innerHeight + 160 && bounds.bottom >= -160) {
                grid.classList.add("is-visible");
            }
        });
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

            previous.disabled = !canScroll;
            next.disabled = !canScroll;
        };


        // Rotate by one card while keeping a continuous three-card window.

        let isMoving = false;

        const finishAfterMotion = (callback) => {
            if (reduceMotion) {
                callback();
                return;
            }

            window.setTimeout(callback, 360);
        };

        const jumpWithoutAnimation = (left) => {
            const previousScrollBehavior =
                viewport.style.scrollBehavior;

            viewport.style.scrollBehavior = "auto";
            viewport.scrollLeft = left;
            viewport.style.scrollBehavior = previousScrollBehavior;
        };

        const moveCarousel = (direction) => {
            if (isMoving || slides.length < 2) {
                return;
            }

            isMoving = true;
            const stepSize = getStepSize();

            if (direction < 0) {
                track.prepend(track.lastElementChild);
                jumpWithoutAnimation(stepSize);

                window.requestAnimationFrame(() => {
                    viewport.scrollTo({
                        left: 0,
                        behavior: reduceMotion ? "auto" : "smooth",
                    });
                });

                finishAfterMotion(() => {
                    isMoving = false;
                });
                return;
            }

            viewport.scrollTo({
                left: stepSize,
                behavior: reduceMotion ? "auto" : "smooth",
            });

            finishAfterMotion(() => {
                track.append(track.firstElementChild);
                jumpWithoutAnimation(0);
                isMoving = false;
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
