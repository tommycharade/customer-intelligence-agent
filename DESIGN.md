---
name: Customer Intelligence
description: A calm account-review workspace with inspectable evidence.
colors:
  primary: "#5b49b7"
  primary-hover: "#4c3ca0"
  primary-soft: "#efedf9"
  canvas: "#f5f6f8"
  surface: "#ffffff"
  navigation: "#262332"
  navigation-active: "#3c344f"
  ink: "#302d3a"
  muted: "#686574"
  line: "#e5e4eb"
  fact-ink: "#36664e"
  fact-surface: "#edf4ef"
  hypothesis-ink: "#7f5c24"
  hypothesis-surface: "#faf3e6"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "29px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-0.035em"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "23px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-0.025em"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "12px"
    fontWeight: 550
    lineHeight: 1.2
rounded:
  tag: "3px"
  field: "5px"
  control: "6px"
  navigation: "7px"
  workspace: "11px"
spacing:
  compact: "8px"
  control: "12px"
  section: "24px"
  workspace: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
  search-field:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.field}"
    padding: "8px 10px"
  navigation-active:
    backgroundColor: "{colors.navigation-active}"
    rounded: "{rounded.navigation}"
    padding: "12px"
  fact-tag:
    backgroundColor: "{colors.fact-surface}"
    textColor: "{colors.fact-ink}"
    rounded: "{rounded.tag}"
    padding: "1px 5px"
  hypothesis-tag:
    backgroundColor: "{colors.hypothesis-surface}"
    textColor: "{colors.hypothesis-ink}"
    rounded: "{rounded.tag}"
    padding: "1px 5px"
  review-workspace:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.workspace}"
---

# Design System: Customer Intelligence

## Overview

**Creative North Star: "The Evidence Desk"**

Cool reading surfaces and dark navigation frame a restrained working interface. The visual hierarchy gives account explanations more space than controls; provenance stays beside the claim it supports.

**Key Characteristics:**
- Compact navigation with generous reading space.
- Violet actions and selection; green and amber evidence labels.
- Quiet borders, modest corners and minimal motion.

This is a record of the implemented React interface in `web/src/style.css` and `web/src/App.tsx`, following the approved contract in `web/index.html`.

## Colors

Primary violet identifies actions, links and selected states. Cool neutral surfaces support reading; the darker navigation separates navigation from account content. Green and amber distinguish observations from hypotheses with explicit text labels.

**The Label Rule.** Color supplements a visible label; it never establishes whether a claim is factual.

## Typography

The application uses the platform system-font stack throughout. The frontmatter records its desktop heading and body roles; account prose and supporting labels use smaller contextual sizes. Mobile account prose and citations become larger where needed for reading and touch.

**The Reading Rule.** Preserve the distinction between a section title, the account claim and the supporting explanation. Use tabular numerals for ranks, usage and dates where the implementation does.

The recorded system font is an implementation fact for this working application, not a prescription for future marketing display typography. Existing small metadata sizes are not a target for reducing new text.

## Layout

The standard desktop shell has a sticky navigation column (214px), a flexible main region and workspace padding (32px). The review surface pairs a ranked account column (290px) with a flexible brief. At widths above 1550px the account column expands to 320px and reading space increases.

At 1200px the shell and account columns narrow; at 900px forms collapse and metadata wraps. At 700px navigation becomes a horizontally scrollable top row, the shortlist stacks above the brief and its rows scroll within 280px. Flexible columns use a zero minimum width to avoid horizontal overflow.

**The Context Rule.** Open evidence beside its claim on desktop. On mobile, treat the evidence drawer as a modal with the background inert and focus contained; closing restores focus to its origin.

## Elevation & Depth

Borders and surface tones create the main hierarchy. The evidence drawer uses the sole structural shadow: `-12px 0 42px rgba(34,21,54,.14)`. The reading workspace and routine controls remain flat.

## Shapes

Corners distinguish compact tags, controls, navigation and the larger workspace without making every region a card. Thin borders separate records and brief sections. Circular status dots accompany text; company initials sit in small rounded squares.

## Components

Primary buttons use violet with white text and a darker hover state. Secondary buttons use a white surface and a fine border. Disabled controls reduce opacity and retain their label. Focus uses a visible outline (3px with a 3px offset); search fields use a focus-within outline.

Navigation uses icon-and-text rows with a quiet active background. Account rows show rank, identity, a short rationale, fit and timing; selection changes the entire row background. Tabs switch between the account brief and contextual chat.

Fact and hypothesis tags precede the claim. Citation controls open a source drawer containing source identity, dates, the supporting excerpt and the saved source text. Explicit unknown timing is a complete state, not an error treatment.

The brief reveals over 180ms with a slight vertical offset. The drawer enters over 220ms with a small horizontal offset. Reduced-motion preferences disable animations and transitions.

## Do's and Don'ts

- Do keep evidence controls adjacent to their claims.
- Do retain explicit fact, hypothesis, uncertainty and synthetic-demo labels.
- Do check keyboard focus, mobile overflow and small-text contrast when adding controls.
- Don't use green or amber as a substitute for a provenance label.
- Don't turn routine reading sections into elevated cards.
- Don't replace unknown information with visually confident claims.
