import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  children: string;
  className?: string;
  compact?: boolean;
}

/** Reusable markdown renderer with dark-theme styling. */
export default function Markdown({ children, className = "", compact = false }: Props) {
  const text = compact ? "text-[11px]" : "text-sm";
  const heading1 = compact ? "text-xs" : "text-lg";
  const heading2 = compact ? "text-[11px]" : "text-base";
  const heading3 = compact ? "text-[11px]" : "text-sm";
  const codeSize = compact ? "text-[10px]" : "text-xs";
  const spacing = compact ? "mb-1" : "mb-2";
  const mt1 = compact ? "mt-2" : "mt-5";
  const mt2 = compact ? "mt-1.5" : "mt-4";
  const mt3 = compact ? "mt-1" : "mt-3";

  return (
    <div className={className}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => (
          <h1 className={`${heading1} font-bold text-gray-100 ${mt1} ${spacing} pb-1 border-b border-bio-border`}>
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 className={`${heading2} font-semibold text-gray-200 ${mt2} ${spacing} pb-1 border-b border-bio-border/50`}>
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className={`${heading3} font-semibold text-gray-200 ${mt3} mb-0.5`}>{children}</h3>
        ),
        p: ({ children }) => (
          <p className={`${text} text-gray-300 leading-relaxed ${spacing}`}>{children}</p>
        ),
        ul: ({ children }) => (
          <ul className={`${text} text-gray-300 list-disc pl-5 ${spacing} space-y-0.5`}>{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className={`${text} text-gray-300 list-decimal pl-5 ${spacing} space-y-0.5`}>{children}</ol>
        ),
        li: ({ children }) => (
          <li className="leading-relaxed">{children}</li>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-gray-100">{children}</strong>
        ),
        em: ({ children }) => (
          <em className="text-gray-400 italic">{children}</em>
        ),
        code: ({ className, children, ...props }) => {
          const isBlock = className?.includes("language-");
          if (isBlock) {
            return (
              <code
                className={`block bg-bio-bg border border-bio-border rounded-lg p-3 ${codeSize} font-mono text-gray-300 overflow-x-auto my-2`}
                {...props}
              >
                {children}
              </code>
            );
          }
          return (
            <code className={`px-1.5 py-0.5 rounded bg-bio-border/60 text-bio-accent ${codeSize} font-mono`} {...props}>
              {children}
            </code>
          );
        },
        pre: ({ children }) => <pre className="my-2">{children}</pre>,
        table: ({ children }) => (
          <div className="overflow-x-auto my-3">
            <table className={`w-full ${codeSize} border-collapse`}>{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-bio-border/30">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="text-left px-3 py-1.5 text-gray-300 font-medium border-b border-bio-border">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-1.5 text-gray-400 border-b border-bio-border/30">{children}</td>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-bio-accent/40 pl-3 my-2 text-gray-400 italic">
            {children}
          </blockquote>
        ),
        hr: () => <hr className="border-bio-border my-4" />,
        a: ({ href, children }) => (
          <a href={href} className="text-bio-accent hover:underline" target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
    </div>
  );
}
