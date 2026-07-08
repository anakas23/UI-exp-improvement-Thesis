/**
 * shop-flow.js
 * ------------
 * Zajednička logika navigacije kroz katalog alata - ISTA na sve 3
 * varijante (isti podaci, isti broj koraka, isti filteri). Razlikuje
 * se samo vizualni raspored zona (definiran u CSS-u svakog HTML filea).
 *
 * Prikazi (views):
 *   - "categories": početni prikaz, 4 kartice kategorija
 *   - "category":   popis artikala JEDNE kategorije (nakon klika na karticu)
 *   - "all":        popis SVIH artikala sa stranice (nakon klika na "Proizvodi" u navu)
 *
 * U prikazima "category" i "all" kategorije su potpuno sakrivene
 * (ne prikazuju se usporedno s popisom artikala).
 *
 * Tok zadatka (identičan na svim varijantama):
 *   1. Kategorije -> klik na "Električni alati" (ili "Proizvodi" u navu za sve odjednom)
 *   2. Popis artikala - filtrira se cijenom (checkboxovi u zoni "sidebar")
 *   3. Klik na artikl (npr. "Kutna brusilica 125mm" - 89 €)
 *   4. Detalj artikla -> klik na "Kupi" (jedini gumb s data-task-target)
 *
 * Traženi artikl NEMA nikakvu posebnu CSS klasu ni oznaku - koristi
 * identičnu .product-card karticu kao i svi ostali artikli. Jedina
 * razlika je interni flag `isTarget`, koji dodaje data-task-target="true"
 * na gumb "Kupi" u detalju.
 */

(function () {
  const CATEGORIES = [
    { id: 'rucni', name: 'Ručni alati', icon: '🔨' },
    { id: 'elektricni', name: 'Električni alati', icon: '⚡' },
    { id: 'vrtni', name: 'Vrtni alati', icon: '🌱' },
    { id: 'mjerni', name: 'Mjerni alati', icon: '📏' },
  ];

  const PRODUCTS = {
    rucni: [
      { id: 'cekic-plavi', name: 'Čekić plavi', price: 12.99, icon: '🔨' },
      { id: 'cekic-crveni', name: 'Čekić crveni', price: 15.99, icon: '🔨' },
      { id: 'odvijac-plosnati', name: 'Odvijač plosnati', price: 4.5, icon: '🪛' },
      { id: 'odvijac-krizni', name: 'Odvijač križni', price: 4.5, icon: '🪛' },
      { id: 'klijesta', name: 'Kliješta kombinirke', price: 9.9, icon: '🔧' },
      { id: 'kljuc-nasadni', name: 'Ključ nasadni set', price: 18.0, icon: '🔧' },
      { id: 'turpija', name: 'Turpija za metal', price: 7.5, icon: '🪚' },
    ],
    elektricni: [
      { id: 'brusilica-230', name: 'Kutna brusilica 230mm', price: 149.0, icon: '⚙️' },
      { id: 'brusilica-ekscentricna', name: 'Ekscentrična brusilica', price: 64.9, icon: '⚙️' },
      { id: 'brusilica-125-crvena', name: 'Kutna brusilica 125mm', price: 99.0, icon: '⚙️' },
      { id: 'busilica-udarna', name: 'Udarna bušilica', price: 79.0, icon: '🔩' },
      { id: 'pila-ubodna', name: 'Ubodna pila', price: 69.0, icon: '🪚' },
      { id: 'brusilica-125-plava', name: 'Kutna brusilica 125mm', price: 89.0, icon: '⚙️', isTarget: true },
      { id: 'brusilica-vibraciona', name: 'Vibraciona brusilica', price: 55.0, icon: '⚙️' },
    ],
    vrtni: [
      { id: 'skare-plave', name: 'Vrtne škare plave', price: 14.9, icon: '✂️' },
      { id: 'skare-crvene', name: 'Vrtne škare crvene', price: 16.9, icon: '✂️' },
      { id: 'grablje', name: 'Grablje', price: 9.5, icon: '🧹' },
      { id: 'lopata', name: 'Lopata', price: 12.0, icon: '🧹' },
      { id: 'motika', name: 'Motika', price: 11.0, icon: '🧹' },
      { id: 'kosa', name: 'Kosa ručna', price: 25.0, icon: '🧹' },
      { id: 'prskalica', name: 'Prskalica za vodu', price: 7.9, icon: '💧' },
    ],
    mjerni: [
      { id: 'metar', name: 'Metalni metar 5m', price: 6.5, icon: '📏' },
      { id: 'libela', name: 'Libela 30cm', price: 11.0, icon: '📏' },
      { id: 'pomicni-mjerac', name: 'Digitalni pomični mjerač', price: 22.0, icon: '📐' },
      { id: 'daljinomjer', name: 'Laserski daljinomjer', price: 45.0, icon: '📐' },
      { id: 'kutomjer', name: 'Kutomjer', price: 8.0, icon: '📐' },
      { id: 'sestar', name: 'Šestar stolarski', price: 9.0, icon: '📐' },
      { id: 'termometar', name: 'Termometar infracrveni', price: 19.0, icon: '🌡️' },
    ],
  };

  const ALL_PRODUCTS = Object.values(PRODUCTS).flat();

  const categoryGrid = document.getElementById('categoryGrid');
  const productGrid = document.getElementById('productGrid');
  const breadcrumb = document.getElementById('breadcrumb');
  const showAllLink = document.querySelector('[data-action="show-all-products"]');
  const homeLink = document.querySelector('[data-action="show-categories"]');

  const priceCheckboxes = document.querySelectorAll('input[name="price-filter"]');

  // 'categories' | 'category' | 'all'
  let currentView = 'categories';
  let currentCategoryId = null;

  function getSelectedValues(checkboxList) {
    return Array.from(checkboxList)
      .filter((cb) => cb.checked)
      .map((cb) => cb.value);
  }

  function matchesPriceFilter(price, selectedRanges) {
    if (selectedRanges.length === 0) return true;
    return selectedRanges.some((range) => {
      if (range === 'under20') return price < 20;
      if (range === 'mid') return price >= 20 && price <= 80;
      if (range === 'over80') return price > 80;
      return true;
    });
  }

  function renderCategories() {
    currentView = 'categories';
    currentCategoryId = null;

    breadcrumb.innerHTML = '';
    productGrid.hidden = true;
    productGrid.innerHTML = '';
    categoryGrid.hidden = false;
    categoryGrid.innerHTML = '';

    CATEGORIES.forEach((cat) => {
      const tile = document.createElement('div');
      tile.className = 'product-card category-tile';
      tile.dataset.zone = 'products';
      tile.innerHTML = `
        <div class="product-image">${cat.icon}</div>
        <div class="product-name">${cat.name}</div>
      `;
      tile.addEventListener('click', () => renderProductList(cat.id, cat.name));
      categoryGrid.appendChild(tile);
    });
  }

  function renderProductList(categoryId, categoryName) {
    currentView = 'category';
    currentCategoryId = categoryId;

    // Kategorije se MORAJU sakriti - ne prikazuju se usporedno s popisom.
    categoryGrid.hidden = true;
    categoryGrid.innerHTML = '';
    productGrid.hidden = false;

    breadcrumb.innerHTML = `
      <button type="button" class="breadcrumb-back" data-zone="products">&larr; Natrag na kategorije</button>
      <span class="breadcrumb-current">${categoryName}</span>
    `;
    breadcrumb.querySelector('.breadcrumb-back').addEventListener('click', renderCategories);

    applyFiltersAndRender();
  }

  function renderAllProducts() {
    currentView = 'all';
    currentCategoryId = null;

    categoryGrid.hidden = true;
    categoryGrid.innerHTML = '';
    productGrid.hidden = false;

    breadcrumb.innerHTML = `
      <button type="button" class="breadcrumb-back" data-zone="products">&larr; Natrag na kategorije</button>
      <span class="breadcrumb-current">Svi proizvodi</span>
    `;
    breadcrumb.querySelector('.breadcrumb-back').addEventListener('click', renderCategories);

    applyFiltersAndRender();
  }

  function getCurrentProductSource() {
    if (currentView === 'all') return ALL_PRODUCTS;
    if (currentView === 'category' && currentCategoryId) return PRODUCTS[currentCategoryId];
    return [];
  }

  function applyFiltersAndRender() {
    const source = getCurrentProductSource();
    if (source.length === 0) return;

    const selectedPrices = getSelectedValues(priceCheckboxes);
    const filtered = source.filter((p) => matchesPriceFilter(p.price, selectedPrices));

    productGrid.innerHTML = '';

    if (filtered.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'no-results';
      empty.textContent = 'Nema artikala koji odgovaraju odabranom filteru.';
      productGrid.appendChild(empty);
      return;
    }

    filtered.forEach((product) => {
      const card = document.createElement('div');
      card.className = 'product-card';
      card.dataset.zone = 'products';
      card.innerHTML = `
        <div class="product-image">${product.icon}</div>
        <div class="product-name">${product.name}</div>
        <div class="product-price">${product.price.toFixed(2).replace('.', ',')} €</div>
      `;
      card.addEventListener('click', (e) => {
        e.stopPropagation();
        openDetail(product);
      });
      productGrid.appendChild(card);
    });
  }

  function openDetail(product) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal-box detail-box">
        <button type="button" class="modal-close" data-zone="products">&times;</button>
        <div class="product-image detail-image">${product.icon}</div>
        <h2>${product.name}</h2>
        <div class="product-price">${product.price.toFixed(2).replace('.', ',')} €</div>
        <button type="button" class="btn-buy is-primary detail-buy" data-zone="cta"${
          product.isTarget ? ' data-task-target="true"' : ''
        }>Kupi</button>
      </div>
    `;
    overlay.querySelector('.modal-close').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });
    document.body.appendChild(overlay);
  }

  // Filteri se primjenjuju odmah čim se checkbox promijeni.
  priceCheckboxes.forEach((cb) => cb.addEventListener('change', applyFiltersAndRender));

  // Klik na "Proizvodi" u navigaciji - prikaži SVE artikle sa stranice.
  if (showAllLink) {
    showAllLink.addEventListener('click', (e) => {
      e.preventDefault();
      renderAllProducts();
    });
  }

  // Klik na "Početna" u navigaciji - vrati na početni prikaz (kategorije).
  if (homeLink) {
    homeLink.addEventListener('click', (e) => {
      e.preventDefault();
      renderCategories();
    });
  }

  renderCategories();
})();