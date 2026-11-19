import { useId, useState } from "react";

import type { Skill } from "@/api/jobs";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useSkillSearch } from "@/hooks/useJobs";
import { cn } from "@/lib/utils";

export interface PickedSkill {
  skillId: number | null; // null: not in the taxonomy yet, added as a custom skill on save
  name: string;
  isCustom: boolean;
}

interface Option {
  key: string;
  label: string;
  pick: PickedSkill;
}

/** "+ Add skill": search the taxonomy by name or alias, or add a new skill by name. */
export function SkillAutocomplete({
  label,
  onPick,
}: {
  label: string;
  onPick: (skill: PickedSkill) => void;
}) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const query = useDebouncedValue(text);
  const { data: found = [], isFetching } = useSkillSearch(query);
  const listId = useId();

  const typed = text.trim();
  const exact = found.some((s: Skill) => s.name.toLowerCase() === typed.toLowerCase());
  const options: Option[] = [
    ...found.map((s: Skill) => ({
      key: `id:${s.id}`,
      label: s.is_custom ? `${s.name} (custom)` : s.name,
      pick: { skillId: s.id, name: s.name, isCustom: s.is_custom },
    })),
    ...(typed && !exact && query.trim() === typed && !isFetching
      ? [
          {
            key: "new",
            label: `Add "${typed}" as a new skill`,
            pick: { skillId: null, name: typed, isCustom: true },
          },
        ]
      : []),
  ];
  const showList = open && typed.length > 0 && options.length > 0;

  function choose(option: Option | undefined) {
    if (!option) return;
    onPick(option.pick);
    setText("");
    setActive(0);
    setOpen(false);
  }

  return (
    <div className="relative">
      <Input
        role="combobox"
        aria-label={label}
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList ? `${listId}-${active}` : undefined}
        placeholder="+ Add skill"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            setOpen(true);
            const step = e.key === "ArrowDown" ? 1 : -1;
            setActive((i) => (options.length ? (i + step + options.length) % options.length : 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(options[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label={`${label}: suggestions`}
          className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-md border bg-popover p-1 text-sm shadow-md"
        >
          {options.map((option, i) => (
            <li
              key={option.key}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={cn(
                "cursor-pointer rounded-sm px-2 py-1.5",
                i === active && "bg-accent text-accent-foreground",
              )}
              // mousedown, not click: the input's blur would close the list first
              onMouseDown={(e) => {
                e.preventDefault();
                choose(option);
              }}
              onMouseEnter={() => setActive(i)}
            >
              {option.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
