#!/bin/sh

PWD=`pwd`

$* 2> /tmp/errors.$$
RESULT=$?

if [ $RESULT -ne 0 ]
then
    exec /usr/bin/perl -x $0 $RESULT /tmp/errors.$$ "$PWD"
fi
exit 0

#!/usr/bin/perl

use strict;

my $result = $ARGV[0];
my $filename = $ARGV[1];
my $pwd = $ARGV[2];

open(FILE, "<$filename") || die "$0: Unable to open file, $!";

my $unresolvedRefError = undef;

while (<FILE>) {
    chomp;

    if (defined $unresolvedRefError) {
        if (m/^  ([^(]+)\(([0-9]+)\)/) {
            my $file = $1;
            my $lineno = $2;

            if (! -f "$pwd/$file") {
                $file =~ s/\.s$/.c/;
            }

            $_ = "$pwd/$file:$lineno:0: Error: $unresolvedRefError";
        } else {
            $unresolvedRefError = undef;
        }
    }

    if (m/^(Unresolved external .* referenced) in:/) {
        $unresolvedRefError = $1;
        $_ = "";
    } elsif (m/^([^(]+)\(([0-9]+)\):(.*)$/) {
        my $file = $1;
        my $lineno = $2;
        my $error = $3;

        $_ = "$pwd/$file:$lineno:0:$error";
    }
    print STDERR "$_\n";
}

unlink($filename);

exit($result);
