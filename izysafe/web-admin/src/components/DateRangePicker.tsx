import { useState } from "react";
import type { DateRange } from "react-day-picker";
import { format } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

export function DateRangePicker({
  value,
  onChange,
  className,
  disabled,
}: {
  value: DateRange | undefined;
  onChange: (range: DateRange | undefined) => void;
  className?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);

  const label =
    value?.from && value?.to
      ? `${format(value.from, "d MMM yyyy")} – ${format(value.to, "d MMM yyyy")}`
      : value?.from
        ? `${format(value.from, "d MMM yyyy")} – …`
        : "Pick a date range";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          disabled={disabled}
          className={cn(
            "w-[19rem] justify-start text-left font-normal",
            !value?.from && "text-muted-foreground",
            className,
          )}
        >
          <CalendarIcon className="size-4" />
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          numberOfMonths={2}
          defaultMonth={value?.from}
          selected={value}
          onSelect={onChange}
        />
      </PopoverContent>
    </Popover>
  );
}
