import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  children: string;
  className?: string;
}

/** Reusable markdown renderer with dark-theme styling. */
export default function Markdown({ children, className = "" }: Props) {
  return (
    <div className={className}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => (
          <h1 className="text-lg font-bold text-gray-100 mt-5 mb-2 pb-1 border-b border-bio-border">
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-base font-semibold text-gray-200 mt-4 mb-2 pb-1 border-b border-bio-border/50">
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-semibold text-gray-200 mt-3 mb-1">{children}</h3>
        ),
        p: ({ children }) => (
          <p className="text-sm text-gray-300 leading-relaxed mb-2">{children}</p>
        ),
        ul: ({ children }) => (
          <ul className="text-sm text-gray-300 list-disc pl-5 mb-2 space-y-0.5">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="text-sm text-gray-300 list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>
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
                className="block bg-bio-bg border border-bio-border rounded-lg p-3 text-xs font-mono text-gray-300 overflow-x-auto my-2"
                {...props}
              >
                {children}
              </code>
            );
          }
          return (
            <code className="px-1.5 py-0.5 rounded bg-bio-border/60 text-bio-accent text-xs font-mono" {...props}>
              {children}
            </code>
          );
        },
        pre: ({ children }) => <pre className="my-2">{children}</pre>,
        table: ({ children }) => (
          <div className="overflow-x-auto my-3">
            <table className="w-full text-xs border-collapse">{children}</table>
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
