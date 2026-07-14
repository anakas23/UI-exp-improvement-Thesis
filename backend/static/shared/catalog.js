/**
 * catalog.js
 * ----------
 * JEDNA statična stranica po varijanti (bez prebacivanja ekrana, bez
 * filtera, bez scroll-kontejnera - obična, duga stranica koja se scrolla
 * kao svaka normalna web stranica).
 *
 * KLJUČNA IZMJENA: redoslijed kategorija OVISI O VARIJANTI. Ovo je
 * namjerna dizajnerska odluka (kao "koju kategoriju shop ističe na vrhu"),
 * ne slučajnost - cilj je da POZICIJA ciljanog artikla na stranici (vrh /
 * sredina / dno) bude ono što se razlikuje IZMEĐU varijanti, a ne nešto što
 * ovisi isključivo o tome koliko je pojedini tester sistematičan u
 * pregledavanju. Time se osigurava da razlike u ponašanju (vrijeme, klikovi
 * prije uspjeha) stvarno dolaze od dizajna stranice, ne od korisnika.
 *
 *   Varijanta A: Električni alati (cilj) NA VRHU
 *   Varijanta B: Električni alati (cilj) NA DNU
 *   Varijanta C: Električni alati (cilj) U SREDINI
 */

(function () {
  const CATEGORY_ORDER = {
    variant_a: ["Električni alati", "Ručni alati", "Vrtni alati", "Mjerni alati"],
    variant_b: ["Ručni alati", "Vrtni alati", "Mjerni alati", "Električni alati"],
    variant_c: ["Ručni alati", "Električni alati", "Vrtni alati", "Mjerni alati"],
  };

  const PRODUCTS_BY_CATEGORY = {
    "Ručni alati": [
      { name: "Čekić plavi", price: 12.99, icon: "🔨" },
      { name: "Čekić crveni", price: 15.99, icon: "🔨" },
      { name: "Odvijač plosnati", price: 4.5, icon: "🪛" },
      { name: "Odvijač križni", price: 4.5, icon: "🪛" },
      { name: "Kliješta kombinirke", price: 9.9, icon: "🔧" },
      { name: "Ključ nasadni set", price: 18.0, icon: "🔧" },
    ],
    "Električni alati": [
      { name: "Kutna brusilica 230mm", price: 149.0, icon: "⚙️" },
      { name: "Ekscentrična brusilica", price: 64.9, icon: "⚙️" },
      { name: "Kutna brusilica 125mm", price: 99.0, icon: "⚙️" },
      { name: "Udarna bušilica", price: 79.0, icon: "🔩" },
      { name: "Kutna brusilica 125mm", price: 89.0, icon: "⚙️", isTarget: true },
      { name: "Vibraciona brusilica", price: 55.0, icon: "⚙️" },
    ],
    "Vrtni alati": [
      { name: "Vrtne škare plave", price: 14.9, icon: "✂️" },
      { name: "Vrtne škare crvene", price: 16.9, icon: "✂️" },
      { name: "Grablje", price: 9.5, icon: "🧹" },
      { name: "Lopata", price: 12.0, icon: "🧹" },
      { name: "Motika", price: 11.0, icon: "🧹" },
      { name: "Prskalica za vodu", price: 7.9, icon: "💧" },
    ],
    "Mjerni alati": [
      { name: "Metalni metar 5m", price: 6.5, icon: "📏" },
      { name: "Libela 30cm", price: 11.0, icon: "📏" },
      { name: "Digitalni pomični mjerač", price: 22.0, icon: "📐" },
      { name: "Laserski daljinomjer", price: 45.0, icon: "📐" },
      { name: "Kutomjer", price: 8.0, icon: "📐" },
      { name: "Termometar infracrveni", price: 19.0, icon: "🌡️" },
    ],
  };

  function slugify(text) {
    return text
      .toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "") // makni hrvatske kvačice
      .replace(/[^a-z0-9]+/g, "-");
  }

  const pageVariant = document.body.dataset.pageVariant;
  const categoryOrder = CATEGORY_ORDER[pageVariant] || Object.keys(PRODUCTS_BY_CATEGORY);

  const catalogEl = document.getElementById("productCatalog");
  const quickNavEl = document.getElementById("categoryQuickNav");

  function renderQuickNav() {
    if (!quickNavEl) return;
    quickNavEl.innerHTML = categoryOrder
      .map((cat) => `<a href="#${slugify(cat)}" data-zone="sidebar">${cat}</a>`)
      .join("");
  }

  function renderCatalog() {
    catalogEl.innerHTML = "";

    categoryOrder.forEach((categoryName) => {
      const section = document.createElement("section");
      section.id = slugify(categoryName);
      section.className = "category-section";

      const heading = document.createElement("h2");
      heading.className = "category-heading";
      heading.textContent = categoryName;
      section.appendChild(heading);

      const grid = document.createElement("div");
      grid.className = "product-grid";

      PRODUCTS_BY_CATEGORY[categoryName].forEach((product) => {
        const card = document.createElement("div");
        card.className = "product-card";
        card.innerHTML = `
          <div class="product-image" data-zone="products">${product.icon}</div>
          <div class="product-name" data-zone="products">${product.name}</div>
          <div class="product-price" data-zone="products">${product.price.toFixed(2).replace(".", ",")} €</div>
          <button type="button" class="btn-buy is-primary" data-zone="cta"${
            product.isTarget ? ' data-task-target="true"' : ""
          }>Kupi</button>
        `;
        grid.appendChild(card);
      });

      section.appendChild(grid);
      catalogEl.appendChild(section);
    });
  }

  // Nav "Početna" - scroll na vrh (obični anchor ponašanje, bez JS stanja)
  const homeLink = document.querySelector('[data-action="scroll-top"]');
  if (homeLink) {
    homeLink.addEventListener("click", (e) => {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  renderQuickNav();
  renderCatalog();
})();