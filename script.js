const menuToggle = document.getElementById("menuToggle");
const navLinks = document.getElementById("navLinks");

menuToggle.addEventListener("click", () => {
  navLinks.classList.toggle("open");
  menuToggle.textContent = navLinks.classList.contains("open") ? "✕" : "☰";
});

const targaryenVideo = document.querySelector(".targaryen video");

const targaryenPlaylist = [
  "videos/targaryen.mp4",
  "videos/targaryen-2.mp4",
  "videos/targaryen-3.mp4"
];

let targaryenIndex = 0;
let targaryenTimer;

targaryenVideo.addEventListener("ended", () => {
  clearTimeout(targaryenTimer);

  targaryenTimer = setTimeout(() => {
    targaryenIndex =
      (targaryenIndex + 1) % targaryenPlaylist.length;

    targaryenVideo.src = targaryenPlaylist[targaryenIndex];
    targaryenVideo.load();
    targaryenVideo.play().catch(() => {});
  }, 2000);
});navLinks.querySelectorAll("a").forEach(link => {
  link.addEventListener("click", () => {
    navLinks.classList.remove("open");
    menuToggle.textContent = "☰";
  });
});

// Character filters
const filterButtons = document.querySelectorAll(".filter-btn");
const characterCards = document.querySelectorAll(".character-card");

filterButtons.forEach(button => {
  button.addEventListener("click", () => {
    filterButtons.forEach(item => item.classList.remove("active"));
    button.classList.add("active");

    const filter = button.dataset.filter;

    characterCards.forEach(card => {
      card.style.display =
        filter === "all" || card.dataset.era === filter ? "" : "none";
    });
  });
});

// Gallery lightbox
const lightbox = document.getElementById("lightbox");
const lightboxImage = document.getElementById("lightboxImage");
const closeLightbox = document.getElementById("closeLightbox");

document.querySelectorAll(".gallery-item").forEach(item => {
  item.addEventListener("click", () => {
    const image = item.querySelector("img");

    if (!image || !image.complete || image.naturalWidth === 0) {
      alert("Pehle is gallery slot mein apni photo add karo.");
      return;
    }

    lightboxImage.src = item.dataset.full;
    lightbox.classList.add("open");
    lightbox.setAttribute("aria-hidden", "false");
  });
});

function hideLightbox() {
  lightbox.classList.remove("open");
  lightbox.setAttribute("aria-hidden", "true");
  lightboxImage.src = "";
}

closeLightbox.addEventListener("click", hideLightbox);

lightbox.addEventListener("click", event => {
  if (event.target === lightbox) hideLightbox();
});

document.addEventListener("keydown", event => {
  if (event.key === "Escape") hideLightbox();
});

document.getElementById("year").textContent = new Date().getFullYear();

const starkVideo = document.querySelector(".stark video");

const starkPlaylist = [
  "videos/stark.mp4",
  "videos/stark-2.mp4",
  "videos/stark-3.mp4"
];

let starkIndex = 0;
let starkTimer;

starkVideo.addEventListener("ended", () => {
  clearTimeout(starkTimer);

  starkTimer = setTimeout(() => {
    starkIndex = (starkIndex + 1) % starkPlaylist.length;
    starkVideo.src = starkPlaylist[starkIndex];
    starkVideo.load();
    starkVideo.play().catch(() => {});
  }, 2000);
});
