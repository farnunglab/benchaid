#!/usr/bin/env python3
from Bio.SeqUtils.ProtParam import ProteinAnalysis
from Bio.Align import PairwiseAligner
import re
import pyperclip


def analyser(input_sequence):
   #Compute all relevant protein parameters
   analysed_seq = ProteinAnalysis(input_sequence)
   analyser.amino_acid_amount = len(input_sequence)
   analyser.amino_acid_count = analysed_seq.count_amino_acids()
   analyser.molecular_weight = round(analysed_seq.molecular_weight(),2)
   analyser.isoelectric_point = round(analysed_seq.isoelectric_point(),1)

   #Count the number of tryptophans and tyrosines in the sequence to use later for molar extinction coefficient calculation.
   tryptophan = analyser.amino_acid_count.get('W', None)
   tyrosine = analyser.amino_acid_count.get('Y', None)

   #Calculate molar extinction coefficient based on extinction coefficients and number of tyrosines and tryptophans
   analyser.molar_extinction_coefficient = ((tyrosine * 1490) + (tryptophan * 5500))
   analyser.absorbance = analyser.molar_extinction_coefficient / analyser.molecular_weight

   #Print the relevant parameters in classical Farnung style
   print("\nNumber of amino acids: {}".format(analyser.amino_acid_amount))
   print("Molecular weight: {}".format(analyser.molecular_weight))
   print("Theoretical pI: {}".format(analyser.isoelectric_point))
   print("Ext. coefficient: {}".format(analyser.molar_extinction_coefficient))
   print("Abs 0.1% (=1 g/L): {}\n".format(round(analyser.absorbance,3)))

#Remove N-terminal tags (if they have a TEV site) to later calculate also protein parameters for the cleaved protein
#It would be interesting to also build a logic to detect if the sample has a C-terminal tag
def tag_remover(input_sequence):
   if "ENLYFQS" in input_sequence:
      tag_remover.tev_present = True
      print("Your sequence contains a TEV site. ProtParams are calculated for the resulting cleavage product.")
      tev_index = input_sequence.find("ENLYFQS")
      tag_remover.endoftev = input_sequence[tev_index+6:]
      print(tag_remover.endoftev)
      analyser(tag_remover.endoftev)
   else:
      tag_remover.tev_present = False
      print("Your sequence does not contain a TEV tag.")

#Detect the presence of a His6 or MBP tag (Could be expanded to detect any tag.)
def tag_detector(input_sequence):
   aligner = PairwiseAligner()
   if aligner.score(input_sequence, "MKIEEGKLVIWINGDKGYNGLAEVGKKFEKDTGIKVTVEHPDKLEEKFPQVAATGDGPDIIFWAHDRFGGYAQSGLLAEITPDKAFQDKLYPFTWDAVRYNGKLIAYPIAVEALSLIYNKDLLPNPPKTWEEIPALDKELKAKGKSALMFNLQEPYFTWPLIAADGGYAFKYENGKYDIKDVGVDNAGAKAGLTFLVDLIKNKHMNADTDYSIAEAAFNKGETAMTINGPWAWSNIDTSKVNYGVTVLPTFKGQPSKPFVGVLSAGINAASPNKELAKEFLENYLLTDEGLEAVNKDKPLGAVALKSYEEELAKDPRIAATMENAQKGEIMPNIPQMSAFWYAVRTAVINAASGRQTVDEALKDAQT") > 200:
      print("Your sequence contains an MBP tag.")
      tag_detector.mbp_present = True
   else:
      tag_detector.mbp_present = False
   if aligner.score(input_sequence, "HHHHHH") > 5:
      print("Your sequence contains a His tag or an internal His region.")
      tag_detector.his_present = True
   else:
      tag_detector.his_present = False

#Generation of purification recommendation
def purification_generator():
   #Check if a HisTrap, Amylose, or HisTrap-Amylose column should be used
   print("\nBased on the protein parameters I recommend the following protein purification procedure:")
   if tag_detector.his_present == True and tag_detector.mbp_present == False:
      print("Use a HisTrap column.")
   elif tag_detector.his_present == False and tag_detector.mbp_present == True:
   	  print("Use a HisTrap column.")
   elif tag_detector.his_present == True and tag_detector.mbp_present == True:
   	  print("Use a HisTrap column, followed by an Amylose column.")

   #Check for the presence of a TEV tag
   if tag_remover.tev_present == True:
   	  print("Cleave your N-terminal tags with TEV and follow the purification with an OrthoNi.")

   #Recommend the use of Q or S column based on pI
   if analyser.isoelectric_point < 6.5:
      print("Your cleaved product has a pI < 6.5. You could use a Q column for ion exchange.")
   elif analyser.isoelectric_point > 8.5:
      print("Your cleaved product has a pI > 8.5. You could use an S column for ion exchange.")

   #Recommend the use of the optimal concentrator
   if analyser.molecular_weight <= 20000:
      print("Use a 3K MWCO concentrator.")
   elif 20000 < analyser.molecular_weight <= 60000:
      print("I recommend to use a 10K MWCO concentrator.")
   elif 60000 < analyser.molecular_weight <= 100000:
      print("I recommend to use a 30K MWCO concentrator.")
   elif 100000 < analyser.molecular_weight <= 200000:
      print("I recommend to use a 50K MWCO concentrator.")
   elif analyser.molecular_weight > 200000:
      print("I recommend to use a 100K MWCO concentrator.")

   #Recommend the appropriate gel filtration/size exclusion column (S75, S200, or Superose 6)
   if analyser.molecular_weight <= 65000:
      print("I recommend to use a S75 column.")
   elif 65000 < analyser.molecular_weight <= 200000:
      print("I recommend to use a S200 column.")
   elif analyser.molecular_weight > 200000:
      print("I recommend to use a Superose 6 column.")

#Main
def main():
   #Obtain amino acid sequence
   while True:
     try:
       input("Please copy your amino acid sequence to your pasteboard, then hit enter!")
       my_seq = pyperclip.paste() #Makes use of pyperclip module
       break
     except ValueError:
       print("Input is not an amino acid sequence.") #If input is not a string the program will stop.
   regex = re.compile('[^a-zA-Z]')
   stripped_my_seq = regex.sub('', my_seq) # Remove all characters that are not part of the alphabet

   analyser(stripped_my_seq)
   tag_detector(stripped_my_seq)
   tag_remover(stripped_my_seq)
   purification_generator()

if __name__ == "__main__":
    main()