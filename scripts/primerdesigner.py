#!/usr/local/bin/python3

import primer3
import re
import textwrap
import Bio
import pyperclip
from Bio import SeqIO, Entrez, Restriction
from Bio.Seq import Seq
from settings import (sequence_dictionary,	global_arg_dictionary_sequencing, global_arg_dictionary_lic, global_arg_dictionary_gibson, email_address, initials) 
from primer3 import calcTm, calcHairpin, calcHomodimer

def primer3_generator(sequence, picking_type):  # Generator to get all three types of primers
    sequence_dictionary.update({'SEQUENCE_TEMPLATE': sequence})  # Load sequence into the dictionary that contains the sequence
    global primers
    global primers_gibson
    if picking_type == 0:  # picking type 0 picks primers for LIC
        primers = primer3.bindings.designPrimers(sequence_dictionary, global_arg_dictionary_lic)
        return primers
    elif picking_type == 1:  # picking type 1 picks primers for Sequencing
        primers = primer3.bindings.designPrimers(sequence_dictionary, global_arg_dictionary_sequencing)
        return primers
    elif picking_type == 2:  # picking type 2 picks primers for longer assemblies, obtaining the ORF from multiple fragments
        iterator = 1
        primers_gibson = {}
        for item in fragments:
            sequence_dictionary.update({'SEQUENCE_TEMPLATE': item})
            primers = primer3.bindings.designPrimers(sequence_dictionary, global_arg_dictionary_gibson)
            for key, value in primers.items():
                if re.match(r"PRIMER_RIGHT_0_SEQUENCE", key):
                    primers_gibson.update({iterator: value})
            iterator += 1
        return primers_gibson


def restriction_tester(sequence_for_digest): #Tests if sequence contains SwaI or PmeI sites
	swai_digest = Restriction.SwaI.search(Seq(sequence_for_digest))
	pmei_digest = Restriction.PmeI.search(Seq(sequence_for_digest))
	if not swai_digest:
		print("No internal SwaI site")
	else:
		print("Internal SwaI site found!")
	if not pmei_digest:
		print("No internal PmeI site")
	else:
		print("Internal PmeI site found!")


def primer_parsing(primer_dictionary,picking_type): #Takes the dictionaries generated from Primer3 and extracts the appropriate primers for each picking type
	global gibson_primers
	gibson_primers = {}
	if picking_type == 0:
		global ligation_primers
		ligation_primers = {}
		for key,value in primers.items():
			if re.match(r"PRIMER_LEFT_\d+_SEQUENCE", key):
				ligation_primers = {key:value}
			if re.match(r"PRIMER_RIGHT_\d+_SEQUENCE", key):
				ligation_primers.update({key:value})
	elif picking_type == 1:
		global sequencing_primers
		sequencing_primers = {}
		for key, value in primers.items():
			if re.match(r"PRIMER_RIGHT_\d+_SEQUENCE", key):
				sequencing_primers.update({key:value}) 
		for key, value in primers.items():
			if re.match(r"PRIMER_LEFT_\d+_SEQUENCE", key):
				sequencing_primers.update({key:value})
	elif picking_type == 2:
		for key, value in primers_gibson.items():
			gibson_primers.update({key:value})
			gibson_forward_primer = Seq(value, generic_dna)
			gibson_primers.update({(str(key)+"r"):str(gibson_forward_primer.reverse_complement())})

def naming_scheme(index_number): # This is the implementation to provide a name for the consecutive rounds of naming and differentiates between the picking types
	for schluessel,primer in ligation_primers.items():
		if re.match(r"PRIMER_LEFT_\d+_SEQUENCE", schluessel):
			print(f'{initials}{index_number}_{gene_name}_LICv1_F\tTACTTCCAATCCAATGCA{primer}')
			index_number += 1
		if re.match(r"PRIMER_RIGHT_\d+_SEQUENCE", schluessel):
			print(f'{initials}{index_number}_{gene_name}_LICv1_R\tTTATCCACTTCCAATGTTATTA{primer}')
			index_number += 1
	if bool(gibson_primers) == True:
		gibson_counter = 1
		for schluessel,primer in gibson_primers.items():
			print(f'{initials}{index_number}_{gene_name}_Gibson_Fragment{gibson_counter}\t{primer}')
			gibson_counter += 1
			index_number += 1
	sequencingNumber = 1
	for schluessel,primer in sequencing_primers.items():
		if sequencingNumber == 1:
			print(f'{initials}{index_number}_{gene_name}_Sequencing{sequencingNumber}_R\t{primer}')
			sequencingNumber += 1
			index_number += 1
		else:
			print(f'{initials}{index_number}_{gene_name}_Sequencing{sequencingNumber}_F\t{primer}')
			sequencingNumber += 1
			index_number += 1

def entry_parsing(accession_input):
	handle = Entrez.efetch(db='nucleotide', id=accession_input, rettype='gb')

	#Parsing of Entry to obtain gene name and sequence of ORF
	for rec in SeqIO.parse(handle, "genbank"):
	   if rec.features:
	       for feature in rec.features:
	           if feature.type == "CDS":
	              #print(feature.qualifiers["gene"])
	               gene_identifier = feature.qualifiers["gene"]
	               global gene_name
	               global gene_sequence
	               gene_name = (gene_identifier[0])
	               gene_sequence = str(feature.location.extract(rec).seq)

def main():
	#Entrez email to pull data from NCBI databases (This email is required.)
	Entrez.email = email_address
	#Ask for accession_code, takes NCBI nucleotide accession code as input
	sequence = ""
	#Ask for the starting number (needs to be an integer)
	while True:
	  try:
	    starting_number = int(input("What is your index number? Only integers allowed. "))
	    break
	  except ValueError:
	    print("Input is not an integer.")
	print("Startnumber is: ",starting_number)

	while True:
		input("Please copy your accession code or sequence to your pasteboard, then hit enter!")
		accession_code = pyperclip.paste()
	#Check if the input is an accession code or a sequence
		if accession_code.startswith(('NM', ' NM', 'XM', ' XM'),0) == True:
			print("You have provided the following accession code: {}".format(accession_code))
			entry_parsing(accession_code)
			break
		elif bool(re.match('^[atcgATCG]+$', accession_code)):
			print("You have provided a sequence.")
			global gene_name
			global gene_sequence
			gene_name = str(input("What is the name of your gene?"))
			gene_sequence = accession_code
			break
		else:
			print("You did not provide a proper sequence or accession code.")
	restriction_tester(gene_sequence)

	#Fragment primer
	if len(gene_sequence) > 5000: # Only generate Gibson Assembly primers for length longer than 5000 bp
		fragment_generation = input(" Your gene is longer than 5000 bp. Do you want to generate primers for Gibson Assembly or CPEC? (y/n) ")
		if fragment_generation == "y" or fragment_generation == "yes":
			global fragments
			gene_length = len(gene_sequence)
			estimated_value = round(gene_length / 3500)
			estimated_length = round(gene_length / estimated_value) + 50
			fragments = gene_sequence[:-estimated_length]
			fragments = textwrap.wrap(fragments, estimated_length)
			for i in range(2):
				primers = primer3_generator(gene_sequence,i)
				primer_parsing(primers,i)
			primers_gibson = primer3_generator(fragments,2)
			primer_parsing(primers_gibson,2)
		else:
			for i in range(2):
				primers = primer3_generator(gene_sequence,i)
				primer_parsing(primers,i)
	else:
		for i in range(2):
			primers = primer3_generator(gene_sequence,i)
			primer_parsing(primers,i)
	naming_scheme(starting_number)

if __name__ == "__main__":
    main()
