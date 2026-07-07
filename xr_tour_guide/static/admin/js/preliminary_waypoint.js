(function () {
  'use strict';

  function findFieldContainer(container, fieldName) {
    if (!container) return null;

    return (
      container.querySelector(`.form-row.field-${fieldName}`) ||
      container.querySelector(`.form-group.field-${fieldName}`) ||
      container.querySelector(`[class*="field-${fieldName}"]`)
    );
  }

  function setFieldVisible(fieldContainer, visible) {
    if (!fieldContainer) return;

    fieldContainer.style.display = visible ? '' : 'none';
  }

  function togglePreliminaryFields(inlineContainer) {
    if (!inlineContainer) return;

    const checkbox = inlineContainer.querySelector(
      'input[name$="-is_preliminary_info"]'
    );

    if (!checkbox) return;

    const placeRow = findFieldContainer(inlineContainer, 'place');
    const coordinatesRow = findFieldContainer(inlineContainer, 'coordinates');

    const updateVisibility = function () {
      const isPreliminary = checkbox.checked;

      // Preliminary waypoints should not expose geolocation fields in the admin UI.
      setFieldVisible(placeRow, !isPreliminary);
      setFieldVisible(coordinatesRow, !isPreliminary);
    };

    if (checkbox.dataset.preliminaryWaypointBound === 'true') {
      updateVisibility();
      return;
    }

    checkbox.addEventListener('change', updateVisibility);
    checkbox.dataset.preliminaryWaypointBound = 'true';

    updateVisibility();
  }

  function getInlineContainerFromCheckbox(checkbox) {
    return (
      checkbox.closest('.inline-related') ||
      checkbox.closest('.dynamic-waypoints') ||
      checkbox.closest('[data-inline-formset]') ||
      checkbox.closest('fieldset') ||
      document
    );
  }

  function initPreliminaryWaypointFields(root) {
    const scope = root || document;

    const checkboxes = scope.querySelectorAll(
      'input[name$="-is_preliminary_info"]'
    );

    checkboxes.forEach(function (checkbox) {
      const inlineContainer = getInlineContainerFromCheckbox(checkbox);
      togglePreliminaryFields(inlineContainer);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initPreliminaryWaypointFields(document);
  });

  // Native Django formset event.
  document.addEventListener('formset:added', function (event) {
    initPreliminaryWaypointFields(event.target);
  });

  // Compatibility with older Django/nested-admin jQuery formset events.
  if (window.django && window.django.jQuery) {
    window.django.jQuery(document).on('formset:added', function (_event, row) {
      initPreliminaryWaypointFields(row);
    });
  }
})();
