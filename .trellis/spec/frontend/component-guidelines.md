# Component Guidelines

> How components are built in this project.

---

## Overview

Route pages are application-owned compositions. Generic administration primitives are copied one at a time through shadcn using the recorded `base-nova` Base UI preset. The repository owns and reviews the generated source; shadcn is not treated as an opaque runtime component library.

---

## Component Structure

- Keep route-level composition in `src/routes/` and reusable primitives in `src/components/ui/`.
- Run shadcn commands from `frontend/`, verify `pnpm dlx shadcn info`, and name the component consumer in the active task.
- Preserve the `base-nova`, Base UI, Lucide, CSS-variable, and alias settings in `components.json`.
- Review every generated file and dependency. Never accept an unrelated global-style or component overwrite.
- Keep providers and router construction under `src/app/`, not inside route components.

---

## Props Conventions

- Define explicit props and extend the underlying native/Base UI props when the wrapper is a primitive.
- Prefer composition through `children` over large boolean prop surfaces.
- Keep product data models out of generic UI primitive props; adapt them in the route or feature boundary.
- Preserve the generated component's `data-slot` attributes because styling and composition may depend on them.

---

## Styling Patterns

- Tailwind CSS 4 and `src/index.css` own styling. Use the local `cn()` helper for conditional classes.
- `src/index.css` owns the civic palette, typography, background grid, reduced-motion rule, and the four-community connection mark.
- Use Lucide only for functional interface icons. Platform marks, agency identity, and brand artwork require reviewed project assets.
- Use CSS/Tailwind for simple transitions. Do not add Motion without a concrete interaction requirement.

---

## Accessibility

- Preserve keyboard operation, visible focus, semantic elements, labels, and accessible names.
- Use Base UI behavior for complex primitives rather than recreating focus or dismissal logic.
- Decorative artwork must be hidden from assistive technology; status and error messages use appropriate live regions.
- All non-essential motion must respect `prefers-reduced-motion`.

---

## Common Mistakes

- Running shadcn before both TypeScript configs expose `@/*`, which can write files into a literal `frontend/@/` directory.
- Adding shadcn components without a named feature consumer.
- Mixing Radix and Base UI implementations without a separately approved migration.
- Replacing the project theme when regenerating a component instead of merging only required framework tokens.
- Using a generic Lucide icon in place of a protected platform or organization mark.
