"use client";

// shadcn/ui Calendar wrapper over react-day-picker v9. Uses the library's base
// stylesheet for layout; the `.rdp-dark` class (see globals.css) recolors it for
// the app's dark theme via react-day-picker's CSS variables.

import * as React from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/style.css";

import { cn } from "@/lib/utils";

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

export function Calendar({ className, ...props }: CalendarProps) {
  return <DayPicker className={cn("rdp-dark", className)} {...props} />;
}
