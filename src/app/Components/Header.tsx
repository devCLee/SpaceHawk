export default function Header() {
  return (
    <header className="fixed top-0 inset-x-0 z-50 h-14 px-10 flex items-center justify-between bg-black/70 backdrop-blur-md">
      <div className="text-sm font-semibold tracking-wide uppercase">
        Logo
      </div>
      <nav className="flex items-center gap-6 text-sm">
        <a href="#menu-item-1" className="hover:text-slate-200 transition-colors">
          Live
        </a>
        <a href="#menu-item-2" className="hover:text-slate-200 transition-colors">
          Sandbox
        </a>
      </nav>
    </header>
  );
}

