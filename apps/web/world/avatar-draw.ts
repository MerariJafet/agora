// Procedural avatar drawing (ADR-0017). Every avatar is generated from the
// closed Avatar Grammar vocabulary with Pixi Graphics primitives — AGORA ships
// no external artwork, loads no remote images, and can never execute an
// avatar payload because there is nothing executable in the grammar.

import { Container, Graphics } from "pixi.js";
import type { AvatarSpec } from "./types";

const BODY_RADIUS = 18;

function hex(value: string): number {
  return Number.parseInt(value.replace("#", "0x"), 16);
}

export function drawAvatar(spec: AvatarSpec): Container {
  const container = new Container();
  const tint = hex(spec.tint);
  const accent = hex(spec.accent ?? spec.tint);
  const g = new Graphics();

  // --- body -----------------------------------------------------------
  switch (spec.body) {
    case "capsule":
      g.roundRect(-13, -22, 26, 44, 13).fill({ color: tint });
      break;
    case "hex": {
      const points: number[] = [];
      for (let i = 0; i < 6; i += 1) {
        const a = (Math.PI / 3) * i - Math.PI / 2;
        points.push(Math.cos(a) * BODY_RADIUS, Math.sin(a) * BODY_RADIUS);
      }
      g.poly(points).fill({ color: tint });
      break;
    }
    case "bot":
      g.roundRect(-16, -18, 32, 36, 6).fill({ color: tint });
      g.rect(-19, -4, 6, 14).fill({ color: accent, alpha: 0.8 });
      g.rect(13, -4, 6, 14).fill({ color: accent, alpha: 0.8 });
      break;
    default:
      g.circle(0, 0, BODY_RADIUS).fill({ color: tint });
  }
  g.stroke({ color: 0x0b0e14, width: 2, alpha: 0.55 });

  // --- visor ------------------------------------------------------------
  switch (spec.visor) {
    case "wide":
      g.roundRect(-12, -8, 24, 9, 4).fill({ color: 0x0b0e14, alpha: 0.85 });
      g.roundRect(-10, -7, 20, 5, 3).fill({ color: accent, alpha: 0.95 });
      break;
    case "hex":
      g.poly([-9, -4, -4, -9, 4, -9, 9, -4, 4, 1, -4, 1])
        .fill({ color: accent, alpha: 0.95 });
      break;
    case "mono":
      g.circle(0, -4, 5).fill({ color: 0x0b0e14 });
      g.circle(0, -4, 3).fill({ color: accent });
      break;
    default:
      g.circle(-5, -4, 3.6).fill({ color: 0x0b0e14 });
      g.circle(5, -4, 3.6).fill({ color: 0x0b0e14 });
      g.circle(-5, -4, 2.2).fill({ color: accent });
      g.circle(5, -4, 2.2).fill({ color: accent });
  }

  // --- expression (mouth line) ------------------------------------------
  switch (spec.expression) {
    case "curious":
      g.moveTo(-4, 8).quadraticCurveTo(0, 12, 5, 6)
        .stroke({ color: 0x0b0e14, width: 1.6, alpha: 0.8 });
      break;
    case "focused":
      g.moveTo(-5, 8).lineTo(5, 8).stroke({ color: 0x0b0e14, width: 1.8, alpha: 0.8 });
      break;
    case "cheerful":
      g.moveTo(-6, 6).quadraticCurveTo(0, 13, 6, 6)
        .stroke({ color: 0x0b0e14, width: 1.8, alpha: 0.85 });
      break;
    default:
      g.moveTo(-3, 8).lineTo(3, 8).stroke({ color: 0x0b0e14, width: 1.2, alpha: 0.6 });
  }

  // --- antenna -----------------------------------------------------------
  const antenna = new Graphics();
  switch (spec.antenna) {
    case "single":
      antenna.moveTo(0, -18).lineTo(0, -30).stroke({ color: accent, width: 2 });
      antenna.circle(0, -32, 3).fill({ color: accent });
      break;
    case "twin":
      antenna.moveTo(-7, -16).lineTo(-11, -29).stroke({ color: accent, width: 2 });
      antenna.moveTo(7, -16).lineTo(11, -29).stroke({ color: accent, width: 2 });
      antenna.circle(-11, -31, 2.5).fill({ color: accent });
      antenna.circle(11, -31, 2.5).fill({ color: accent });
      break;
    case "dish":
      antenna.moveTo(0, -18).lineTo(0, -27).stroke({ color: accent, width: 2 });
      antenna.ellipse(0, -31, 9, 5).fill({ color: accent, alpha: 0.85 });
      break;
    case "telescope":
      antenna.moveTo(0, -18).lineTo(6, -30).stroke({ color: accent, width: 2.5 });
      antenna.rect(4, -36, 6, 8).fill({ color: accent, alpha: 0.9 });
      break;
    default:
      break;
  }

  // --- accessory ---------------------------------------------------------
  const accessory = new Graphics();
  switch (spec.accessory) {
    case "satchel":
      accessory.roundRect(10, 2, 12, 10, 3).fill({ color: accent, alpha: 0.85 });
      break;
    case "book":
      accessory.roundRect(-24, -2, 12, 14, 2).fill({ color: accent, alpha: 0.9 });
      accessory.moveTo(-18, -2).lineTo(-18, 12).stroke({ color: 0x0b0e14, width: 1 });
      break;
    case "wrench":
      accessory.roundRect(14, -8, 4, 18, 2).fill({ color: accent });
      accessory.circle(16, -10, 4).stroke({ color: accent, width: 3 });
      break;
    case "scanner":
      accessory.arc(0, 0, 26, -0.5, 0.5).stroke({ color: accent, width: 2, alpha: 0.65 });
      accessory.arc(0, 0, 32, -0.35, 0.35).stroke({ color: accent, width: 1.5, alpha: 0.4 });
      break;
    default:
      break;
  }

  // --- emblem -------------------------------------------------------------
  const emblem = new Graphics();
  const ec = { color: 0x0b0e14, alpha: 0.75 };
  switch (spec.emblem) {
    case "star":
      emblem.star(0, 4, 5, 5).fill(ec);
      break;
    case "atom":
      emblem.ellipse(0, 4, 7, 3).stroke({ ...ec, width: 1.4 });
      emblem.ellipse(0, 4, 3, 7).stroke({ ...ec, width: 1.4 });
      break;
    case "code":
      emblem.moveTo(-6, 1).lineTo(-9, 4).lineTo(-6, 7).stroke({ ...ec, width: 1.4 });
      emblem.moveTo(6, 1).lineTo(9, 4).lineTo(6, 7).stroke({ ...ec, width: 1.4 });
      break;
    case "sigma":
      emblem.moveTo(-5, 0).lineTo(5, 0).lineTo(-2, 4).lineTo(5, 8).lineTo(-5, 8)
        .stroke({ ...ec, width: 1.4 });
      break;
    case "compass":
      emblem.circle(0, 4, 6).stroke({ ...ec, width: 1.3 });
      emblem.moveTo(-3, 7).lineTo(3, 1).stroke({ ...ec, width: 1.5 });
      break;
    default:
      break;
  }

  container.addChild(g, antenna, accessory, emblem);
  return container;
}

/** Cheap far-LOD representation: a tinted dot, no detail, no interaction. */
export function drawAvatarDot(spec: AvatarSpec): Graphics {
  return new Graphics().circle(0, 0, 5).fill({ color: hex(spec.tint), alpha: 0.9 });
}
