const deck = document.querySelector("#deck");
const slides = [...document.querySelectorAll(".slide")];
const dots = [...document.querySelectorAll(".dots button")];
const prevButton = document.querySelector("#prev");
const nextButton = document.querySelector("#next");
const slideIndex = document.querySelector("#slide-index");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function currentIndex() {
  const mark = deck.scrollTop + deck.clientHeight * 0.35;
  let index = 0;
  slides.forEach((slide, i) => {
    if (slide.offsetTop <= mark) index = i;
  });
  return index;
}

function setCurrent(index) {
  dots.forEach((dot, i) => {
    if (i === index) dot.setAttribute("aria-current", "true");
    else dot.removeAttribute("aria-current");
  });
  prevButton.disabled = index === 0;
  nextButton.disabled = index === slides.length - 1;
  slideIndex.textContent = String(index + 1);
}

function scrollBehavior() {
  return reducedMotion ? "auto" : "smooth";
}

function goTo(index, focusSlide) {
  const next = Math.max(0, Math.min(slides.length - 1, index));
  slides[next].scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  if (focusSlide) slides[next].focus({ preventScroll: true });
  history.replaceState(null, "", `#${slides[next].id}`);
}

function step(delta) {
  const index = currentIndex();
  const slide = slides[index];
  const max = slide.scrollHeight - slide.clientHeight;
  const behavior = scrollBehavior();
  if (delta > 0 && slide.scrollTop < max - 24) {
    slide.scrollTo({ top: Math.min(max, slide.scrollTop + slide.clientHeight * 0.86), behavior });
    return;
  }
  if (delta < 0 && slide.scrollTop > 24) {
    slide.scrollTo({ top: Math.max(0, slide.scrollTop - slide.clientHeight * 0.86), behavior });
    return;
  }
  goTo(index + delta, true);
}

deck.addEventListener(
  "scroll",
  () => {
    setCurrent(currentIndex());
  },
  { passive: true },
);

dots.forEach((dot, index) => {
  dot.addEventListener("click", () => goTo(index, false));
});
prevButton.addEventListener("click", () => step(-1));
nextButton.addEventListener("click", () => step(1));

document.addEventListener("keydown", (event) => {
  const tag = document.activeElement && document.activeElement.tagName;
  if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
  if (event.key === "ArrowDown" || event.key === "ArrowRight" || event.key === "PageDown") {
    event.preventDefault();
    step(1);
  } else if (event.key === "ArrowUp" || event.key === "ArrowLeft" || event.key === "PageUp") {
    event.preventDefault();
    step(-1);
  } else if (event.key === "Home") {
    event.preventDefault();
    goTo(0, true);
  } else if (event.key === "End") {
    event.preventDefault();
    goTo(slides.length - 1, true);
  }
});

document.querySelector(".skip").addEventListener("click", (event) => {
  event.preventDefault();
  goTo(0, true);
});

const hash = window.location.hash.replace("#", "");
const start = slides.findIndex((slide) => slide.id === hash);
if (start > 0) {
  slides[start].scrollIntoView({ behavior: "auto", block: "start" });
}
setCurrent(currentIndex());
