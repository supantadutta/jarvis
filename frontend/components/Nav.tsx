import Link from "next/link";

const PAGES = [
  ["/", "Chat"],
  ["/tasks", "Tasks"],
  ["/agents", "Agents"],
  ["/models", "Models"],
  ["/approvals", "Approvals"],
  ["/tools", "Tools"],
  ["/memory", "Memory"],
  ["/documents", "Documents"],
  ["/workflows", "Workflows"],
  ["/soc", "SOC"],
  ["/evaluations", "Evaluations"],
  ["/credentials", "Credentials"],
  ["/audit", "Audit"],
  ["/settings", "Settings"],
  ["/health", "Health"],
];

export default function Nav() {
  return (
    <nav className="w-52 shrink-0 border-r border-neutral-800 p-4 space-y-1">
      <div className="text-xl font-bold mb-4">JARVIS</div>
      {PAGES.map(([href, label]) => (
        <Link
          key={href}
          href={href}
          className="block rounded px-3 py-2 text-sm hover:bg-neutral-800"
        >
          {label}
        </Link>
      ))}
      <p className="pt-4 text-xs text-neutral-500">
        Local-first multi-AI assistant
      </p>
    </nav>
  );
}
