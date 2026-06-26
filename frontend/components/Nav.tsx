"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArcReactor } from "./Hud";

const GROUPS: [string, [string, string][]][] = [
  ["Core", [["/", "Console"], ["/agent", "Agent"], ["/brain", "Brain v2"], ["/chat", "Chat"]]],
  ["Ops", [["/tasks", "Tasks"], ["/workflows", "Workflows"], ["/approvals", "Approvals"], ["/audit", "Audit"]]],
  ["Mind", [["/models", "Models"], ["/agents", "Agents"], ["/memory", "Memory"],
            ["/documents", "Documents"], ["/evaluations", "Evaluations"]]],
  ["Sys", [["/soc", "SOC"], ["/tools", "Tools"], ["/credentials", "Credentials"],
           ["/settings", "Settings"], ["/health", "Health"]]],
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="w-56 shrink-0 border-r p-4 space-y-4 overflow-y-auto"
      style={{ borderColor: "var(--line)", background: "rgba(4,7,14,0.7)", backdropFilter: "blur(6px)" }}>
      <div className="flex items-center gap-3 mb-2">
        <ArcReactor size={40} />
        <div>
          <div className="display text-xl glow-text leading-none">JARVIS</div>
          <div className="label">v2 · online</div>
        </div>
      </div>
      {GROUPS.map(([group, items]) => (
        <div key={group}>
          <div className="label mb-1 opacity-70">{group}</div>
          <div className="space-y-0.5">
            {items.map(([href, lbl]) => {
              const active = path === href;
              return (
                <Link key={href} href={href}
                  className="block rounded px-3 py-1.5 text-sm transition-all"
                  style={active
                    ? { color: "#eafdff", background: "rgba(34,211,238,0.14)",
                        boxShadow: "inset 2px 0 0 var(--cyan), 0 0 14px var(--glow)" }
                    : { color: "var(--muted)" }}>
                  {active ? "▸ " : "  "}{lbl}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
