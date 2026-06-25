(function () {
  "use strict";

  var CONFIG = {
    cards: {
      noun: "cards",
      filters: [
        { key: "section", label: "Character / Pool" },
        { key: "column", column: 2, label: "Cost" },
        { key: "column", column: 3, label: "Type" },
        { key: "column", column: 4, label: "Rarity" }
      ]
    },
    relics: {
      noun: "relics",
      filters: [
        { key: "section", label: "Rarity" },
        { key: "column", column: 2, label: "Pool" }
      ]
    },
    enemies: {
      noun: "enemies",
      filters: [
        { key: "column", column: 2, label: "Class" },
        { key: "column", column: 4, label: "Act", multiple: true }
      ]
    }
  };

  function text(value) {
    return (value || "").trim().replace(/\s+/g, " ");
  }

  function normalize(value) {
    return text(value).toLowerCase();
  }

  function optionValues(rows, filter) {
    var values = new Set();
    rows.forEach(function (row) {
      var value = filter.key === "section"
        ? row.dataset.wikiSection
        : text(row.cells[filter.column] && row.cells[filter.column].textContent);
      if (filter.multiple) {
        value.split(",").forEach(function (part) {
          if (text(part) !== "-") values.add(text(part));
        });
      } else if (value && value !== "-") {
        values.add(value);
      }
    });
    return Array.from(values).sort(function (a, b) {
      return a.localeCompare(b, undefined, { numeric: true });
    });
  }

  function field(label, control) {
    var wrapper = document.createElement("label");
    wrapper.className = "wiki-browser__field";
    var caption = document.createElement("span");
    caption.textContent = label;
    wrapper.append(caption, control);
    return wrapper;
  }

  function tableWrapper(table) {
    return table.closest(".md-typeset__scrollwrap") || table;
  }

  function collectTables(root, kind) {
    var main = root.closest("article") || document.querySelector("main");
    var tables = [];
    var section = "";
    main.querySelectorAll("h2, table").forEach(function (node) {
      if (node.tagName === "H2") {
        section = text(node.textContent);
        return;
      }
      var headers = Array.from(node.querySelectorAll("thead th")).map(function (header) {
        return text(header.textContent);
      });
      var expectedName = kind === "cards" ? "Card" : kind === "relics" ? "Relic" : "Enemy";
      if (!headers.includes(expectedName)) return;
      node.classList.add("wiki-browser-table");
      node.querySelectorAll("tbody tr").forEach(function (row) {
        row.dataset.wikiSection = section;
      });
      tables.push({ table: node, heading: node.closest(".md-typeset__scrollwrap")?.previousElementSibling });
    });
    return tables;
  }

  function initialize(root) {
    if (root.dataset.wikiBrowserReady) return;
    var kind = root.dataset.wikiBrowser;
    var config = CONFIG[kind];
    if (!config) return;

    var tables = collectTables(root, kind);
    var rows = tables.flatMap(function (item) {
      return Array.from(item.table.querySelectorAll("tbody tr"));
    });
    if (!rows.length) return;

    root.dataset.wikiBrowserReady = "true";
    root.setAttribute("role", "search");
    root.setAttribute("aria-label", "Filter " + config.noun);

    var controls = document.createElement("div");
    controls.className = "wiki-browser__controls";
    var query = document.createElement("input");
    query.type = "search";
    query.placeholder = "Search " + config.noun;
    query.setAttribute("aria-label", "Search " + config.noun);
    controls.append(field("Search", query));

    var selects = config.filters.map(function (filter) {
      var select = document.createElement("select");
      select.setAttribute("aria-label", filter.label);
      var all = document.createElement("option");
      all.value = "";
      all.textContent = "All";
      select.append(all);
      optionValues(rows, filter).forEach(function (value) {
        var option = document.createElement("option");
        option.value = normalize(value);
        option.textContent = value;
        select.append(option);
      });
      controls.append(field(filter.label, select));
      return { element: select, filter: filter };
    });

    var reset = document.createElement("button");
    reset.type = "button";
    reset.className = "wiki-browser__reset";
    reset.textContent = "Reset";
    controls.append(reset);

    var status = document.createElement("output");
    status.className = "wiki-browser__status";
    status.setAttribute("aria-live", "polite");
    root.append(controls, status);

    function apply() {
      var queryValue = normalize(query.value);
      var visible = 0;
      rows.forEach(function (row) {
        var matches = !queryValue || normalize(row.textContent).includes(queryValue);
        selects.forEach(function (entry) {
          if (!matches || !entry.element.value) return;
          var filter = entry.filter;
          var value = filter.key === "section"
            ? row.dataset.wikiSection
            : text(row.cells[filter.column] && row.cells[filter.column].textContent);
          var normalized = filter.multiple
            ? value.split(",").map(normalize)
            : [normalize(value)];
          matches = normalized.includes(entry.element.value);
        });
        row.hidden = !matches;
        if (matches) visible += 1;
      });

      tables.forEach(function (item) {
        var hasVisibleRows = Array.from(item.table.querySelectorAll("tbody tr")).some(function (row) {
          return !row.hidden;
        });
        tableWrapper(item.table).hidden = !hasVisibleRows;
        if (item.heading && item.heading.tagName === "H2") item.heading.hidden = !hasVisibleRows;
      });
      status.value = visible + " of " + rows.length + " " + config.noun;
      reset.disabled = !query.value && selects.every(function (entry) { return !entry.element.value; });
    }

    query.addEventListener("input", apply);
    selects.forEach(function (entry) { entry.element.addEventListener("change", apply); });
    reset.addEventListener("click", function () {
      query.value = "";
      selects.forEach(function (entry) { entry.element.value = ""; });
      apply();
      query.focus();
    });
    apply();
  }

  function initializeAll() {
    document.querySelectorAll("[data-wiki-browser]").forEach(initialize);
  }

  document.addEventListener("DOMContentLoaded", initializeAll);
  if (typeof document$ !== "undefined") document$.subscribe(initializeAll);
}());
