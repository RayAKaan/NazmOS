'use client';

import * as React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { Button } from './Button';

interface ButtonWithIconProps extends React.ComponentProps<typeof Button> {
  icon?: React.ReactNode;
}

export function ButtonWithIcon({ 
  children, 
  className = '', 
  icon = <ArrowUpRight size={16} />,
  ...props 
}: ButtonWithIconProps) {
  return (
    <Button 
      className={`relative rounded-none overflow-hidden group pl-6 pr-14 ${className}`}
      {...props}
    >
      <span className="relative z-10">{children}</span>
      <div className="absolute right-1 top-1/2 -translate-y-1/2 w-10 h-10 bg-accent-primary text-bg-primary rounded-none flex items-center justify-center transition-all duration-300 group-hover:right-[calc(100%-44px)]">
        {icon}
      </div>
    </Button>
  );
}
