import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker, getDefaultClassNames } from "react-day-picker";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

/** shadcn-style calendar wrapping react-day-picker v10. */
function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: CalendarProps) {
  const d = getDefaultClassNames();
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn("p-3", className)}
      classNames={{
        months: cn("relative flex flex-col gap-2 sm:flex-row", d.months),
        month: cn("flex flex-col gap-4", d.month),
        month_caption: cn(
          "relative flex h-9 items-center justify-center pt-1",
          d.month_caption,
        ),
        caption_label: cn("text-sm font-medium", d.caption_label),
        nav: cn(
          "absolute inset-x-0 top-0 flex items-center justify-between",
          d.nav,
        ),
        button_previous: cn(
          buttonVariants({ variant: "outline" }),
          "size-7 bg-transparent p-0 opacity-50 hover:opacity-100",
          d.button_previous,
        ),
        button_next: cn(
          buttonVariants({ variant: "outline" }),
          "size-7 bg-transparent p-0 opacity-50 hover:opacity-100",
          d.button_next,
        ),
        month_grid: cn("w-full border-collapse space-y-1", d.month_grid),
        weekdays: cn("flex", d.weekdays),
        weekday: cn(
          "w-8 rounded-md text-[0.8rem] font-normal text-muted-foreground",
          d.weekday,
        ),
        week: cn("mt-2 flex w-full", d.week),
        day: cn(
          "relative p-0 text-center text-sm focus-within:relative focus-within:z-20 [&:has([aria-selected])]:bg-accent [&:has([aria-selected].day-range-end)]:rounded-r-md first:[&:has([aria-selected])]:rounded-l-md last:[&:has([aria-selected])]:rounded-r-md",
          d.day,
        ),
        day_button: cn(
          buttonVariants({ variant: "ghost" }),
          "size-8 p-0 font-normal aria-selected:opacity-100",
          d.day_button,
        ),
        range_start: cn(
          "day-range-start rounded-l-md bg-primary text-primary-foreground",
          d.range_start,
        ),
        range_end: cn(
          "day-range-end rounded-r-md bg-primary text-primary-foreground",
          d.range_end,
        ),
        range_middle: cn(
          "rounded-none aria-selected:bg-accent aria-selected:text-accent-foreground",
          d.range_middle,
        ),
        selected: cn(
          "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground focus:bg-primary focus:text-primary-foreground",
          d.selected,
        ),
        today: cn("rounded-md bg-accent text-accent-foreground", d.today),
        outside: cn(
          "text-muted-foreground aria-selected:text-muted-foreground",
          d.outside,
        ),
        disabled: cn("text-muted-foreground opacity-50", d.disabled),
        hidden: cn("invisible", d.hidden),
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation }) => {
          const Icon = orientation === "left" ? ChevronLeft : ChevronRight;
          return <Icon className="size-4" />;
        },
      }}
      {...props}
    />
  );
}
Calendar.displayName = "Calendar";

export { Calendar };
