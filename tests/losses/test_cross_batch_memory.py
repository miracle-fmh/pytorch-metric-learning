import unittest 
from .. import TEST_DTYPES
import torch
from pytorch_metric_learning.utils import loss_and_miner_utils as lmu
from pytorch_metric_learning.utils import common_functions as c_f
from pytorch_metric_learning.losses import CrossBatchMemory, ContrastiveLoss, NTXentLoss
from pytorch_metric_learning.miners import PairMarginMiner, TripletMarginMiner, MultiSimilarityMiner, DistanceWeightedMiner

class TestCrossBatchMemory(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        self.embedding_size = 128
        self.memory_size = 321
        self.device = torch.device("cuda")

    def test_remove_self_comparisons(self):
        for dtype in TEST_DTYPES:
            batch_size = 32
            loss = CrossBatchMemory(loss=None, embedding_size=self.embedding_size, memory_size=self.memory_size)
            loss.embedding_memory = loss.embedding_memory.to(self.device).type(dtype)
            loss.label_memory = loss.label_memory.to(self.device)
            embeddings = torch.randn(batch_size, self.embedding_size).to(self.device).type(dtype)
            labels = torch.randint(0, 10, (batch_size,)).to(self.device)
            num_tuples = 1000
            num_non_identical = 147

            for i in range(30):
                loss.add_to_memory(embeddings, labels, batch_size)
                for identical in [True, False]:
                    # triplets
                    a = torch.randint(0,batch_size,(num_tuples,)).to(self.device)
                    p = a + loss.curr_batch_idx[0]
                    if not identical:
                        rand_diff_idx = torch.randint(0, num_tuples, (num_non_identical,)).to(self.device)
                        offsets = torch.randint(-self.memory_size+1, self.memory_size, (num_non_identical,)).to(self.device)
                        offsets[offsets==0] = 1
                        p[rand_diff_idx] += offsets
                    p %= self.memory_size
                    n = torch.randint(0,batch_size,(num_tuples,)).to(self.device)
                    a_new,p_new,n_new = loss.remove_self_comparisons((a,p,n))
                    if identical:
                        self.assertTrue(len(a_new)==len(p_new)==len(n_new)==0)
                    else:
                        triplets = set([(x.item(),y.item(),z.item()) for x,y,z in zip(a[rand_diff_idx],p[rand_diff_idx],n[rand_diff_idx])])
                        triplets_new = set([(x.item(),y.item(),z.item()) for x,y,z in zip(a_new,p_new,n_new)])
                        self.assertTrue(set(triplets) == set(triplets_new))

                    # pairs
                    a1 = torch.randint(0,batch_size,(num_tuples,)).to(self.device)
                    p = a1 + loss.curr_batch_idx[0]
                    if not identical:
                        rand_diff_idx = torch.randint(0, num_tuples, (num_non_identical,)).to(self.device)
                        offsets = torch.randint(-self.memory_size+1, self.memory_size, (num_non_identical,)).to(self.device)
                        offsets[offsets==0] = 1
                        p[rand_diff_idx] += offsets
                    p %= self.memory_size
                    a2 = torch.randint(0,batch_size,(num_tuples,)).to(self.device)
                    n = (torch.randint(0,batch_size,(num_tuples,)).to(self.device) + loss.curr_batch_idx[0]) % self.memory_size
                    a1_new, p_new, a2_new, n_new = loss.remove_self_comparisons((a1, p, a2, n))
                    if identical:
                        self.assertTrue(len(a1_new) == len(p_new) == 0)
                    else:
                        pos_pairs = set([(x.item(),y.item()) for x,y in zip(a1[rand_diff_idx],p[rand_diff_idx])])
                        pos_pairs_new = set([(x.item(),y.item()) for x,y in zip(a1_new,p_new)])
                        self.assertTrue(set(pos_pairs) == set(pos_pairs_new))

                    self.assertTrue(torch.equal(a2_new, a2))
                    self.assertTrue(torch.equal(n_new, n))


    def test_sanity_check(self):
        # cross batch memory with batch_size == memory_size should be equivalent to just using the inner loss function
        for dtype in TEST_DTYPES:
            for memory_size in range(20, 40, 5):
                inner_loss = NTXentLoss(temperature=0.1)
                inner_miner = TripletMarginMiner(margin=0.1)
                loss = CrossBatchMemory(loss=inner_loss, embedding_size=self.embedding_size, memory_size=memory_size)
                loss_with_miner = CrossBatchMemory(loss=inner_loss, embedding_size=self.embedding_size, memory_size=memory_size, miner=inner_miner)
                for i in range(10):
                    embeddings = torch.randn(memory_size, self.embedding_size).to(self.device).type(dtype)
                    labels = torch.randint(0, 4, (memory_size,)).to(self.device)
                    inner_loss_val = inner_loss(embeddings, labels)
                    loss_val = loss(embeddings, labels)
                    self.assertTrue(torch.isclose(inner_loss_val, loss_val))

                    triplets = inner_miner(embeddings, labels)
                    inner_loss_val = inner_loss(embeddings, labels, triplets)
                    loss_val = loss_with_miner(embeddings, labels)
                    self.assertTrue(torch.isclose(inner_loss_val, loss_val))


    def test_with_distance_weighted_miner(self):
        for dtype in TEST_DTYPES:
            memory_size = 256
            inner_loss = NTXentLoss(temperature=0.1)
            inner_miner = DistanceWeightedMiner(cutoff=0.5, nonzero_loss_cutoff=1.4)
            loss_with_miner = CrossBatchMemory(loss=inner_loss, embedding_size=2, memory_size=memory_size, miner=inner_miner)
            for i in range(20):
                embedding_angles = torch.arange(0, 32)
                embeddings = torch.tensor([c_f.angle_to_coord(a) for a in embedding_angles], requires_grad=True, dtype=dtype).to(self.device) #2D embeddings
                labels = torch.randint(low=0, high=10, size=(32,)).to(self.device)
                loss_val = loss_with_miner(embeddings, labels)
                loss_val.backward()
                self.assertTrue(True) # just check if we got here without an exception


    def test_loss(self):
        for dtype in TEST_DTYPES:
            num_labels = 10
            num_iter = 10
            batch_size = 32
            inner_loss = ContrastiveLoss()
            inner_miner = MultiSimilarityMiner(0.3)
            outer_miner = MultiSimilarityMiner(0.2)
            self.loss = CrossBatchMemory(loss=inner_loss, embedding_size=self.embedding_size, memory_size=self.memory_size)
            self.loss_with_miner = CrossBatchMemory(loss=inner_loss, miner=inner_miner, embedding_size=self.embedding_size, memory_size=self.memory_size)
            self.loss_with_miner2 = CrossBatchMemory(loss=inner_loss, miner=inner_miner, embedding_size=self.embedding_size, memory_size=self.memory_size)
            all_embeddings = torch.tensor([], dtype=dtype).to(self.device)
            all_labels = torch.LongTensor([]).to(self.device)
            for i in range(num_iter):
                embeddings = torch.randn(batch_size, self.embedding_size).to(self.device).type(dtype)
                labels = torch.randint(0,num_labels,(batch_size,)).to(self.device)
                loss = self.loss(embeddings, labels)
                loss_with_miner = self.loss_with_miner(embeddings, labels)
                oa1, op, oa2, on = outer_miner(embeddings, labels)
                loss_with_miner_and_input_indices = self.loss_with_miner2(embeddings, labels, (oa1, op, oa2, on))
                all_embeddings = torch.cat([all_embeddings, embeddings])
                all_labels = torch.cat([all_labels, labels])

                # loss with no inner miner
                indices_tuple = lmu.get_all_pairs_indices(labels, all_labels)
                a1,p,a2,n = self.loss.remove_self_comparisons(indices_tuple)
                p = p+batch_size
                n = n+batch_size
                correct_loss = inner_loss(torch.cat([embeddings, all_embeddings], dim=0), torch.cat([labels, all_labels], dim=0), (a1,p,a2,n))
                self.assertTrue(torch.isclose(loss, correct_loss))

                # loss with inner miner
                indices_tuple = inner_miner(embeddings, labels, all_embeddings, all_labels)
                a1,p,a2,n = self.loss_with_miner.remove_self_comparisons(indices_tuple)
                p = p+batch_size
                n = n+batch_size
                correct_loss_with_miner = inner_loss(torch.cat([embeddings, all_embeddings], dim=0), torch.cat([labels, all_labels], dim=0), (a1,p,a2,n))
                self.assertTrue(torch.isclose(loss_with_miner, correct_loss_with_miner))

                # loss with inner and outer miner
                indices_tuple = inner_miner(embeddings, labels, all_embeddings, all_labels)
                a1,p,a2,n = self.loss_with_miner2.remove_self_comparisons(indices_tuple)
                p = p+batch_size
                n = n+batch_size
                a1 = torch.cat([oa1, a1])
                p = torch.cat([op, p])
                a2 = torch.cat([oa2, a2])
                n = torch.cat([on, n])
                correct_loss_with_miner_and_input_indice = inner_loss(torch.cat([embeddings, all_embeddings], dim=0), torch.cat([labels, all_labels], dim=0), (a1,p,a2,n))
                self.assertTrue(torch.isclose(loss_with_miner_and_input_indices, correct_loss_with_miner_and_input_indice))


    def test_queue(self):
        for dtype in TEST_DTYPES:
            batch_size = 32
            self.loss = CrossBatchMemory(loss=ContrastiveLoss(), embedding_size=self.embedding_size, memory_size=self.memory_size)
            for i in range(30):
                embeddings = torch.randn(batch_size, self.embedding_size).to(self.device).type(dtype)
                labels = torch.arange(batch_size).to(self.device)
                q = self.loss.queue_idx
                self.assertTrue(q==(i*batch_size)%self.memory_size)
                loss = self.loss(embeddings, labels)

                start_idx = q
                if q+batch_size == self.memory_size:
                    end_idx = self.memory_size
                else:
                    end_idx = (q+batch_size)%self.memory_size
                if start_idx < end_idx:
                    self.assertTrue(torch.equal(embeddings, self.loss.embedding_memory[start_idx:end_idx]))
                    self.assertTrue(torch.equal(labels, self.loss.label_memory[start_idx:end_idx]))
                else:
                    correct_embeddings = torch.cat([self.loss.embedding_memory[start_idx:], self.loss.embedding_memory[:end_idx]], dim=0)
                    correct_labels = torch.cat([self.loss.label_memory[start_idx:], self.loss.label_memory[:end_idx]], dim=0)
                    self.assertTrue(torch.equal(embeddings, correct_embeddings))
                    self.assertTrue(torch.equal(labels, correct_labels))

    def test_shift_indices_tuple(self):
        for dtype in TEST_DTYPES:
            batch_size = 32
            pair_miner = PairMarginMiner(pos_margin=0, neg_margin=1)
            triplet_miner = TripletMarginMiner(margin=1)
            self.loss = CrossBatchMemory(loss=ContrastiveLoss(), embedding_size=self.embedding_size, memory_size=self.memory_size)
            for i in range(30):
                embeddings = torch.randn(batch_size, self.embedding_size).to(self.device).type(dtype)
                labels = torch.arange(batch_size).to(self.device)
                loss = self.loss(embeddings, labels)
                all_labels = torch.cat([labels, self.loss.label_memory], dim=0)

                indices_tuple = lmu.get_all_pairs_indices(labels, self.loss.label_memory)
                shifted = c_f.shift_indices_tuple(indices_tuple, batch_size)
                self.assertTrue(torch.equal(indices_tuple[0], shifted[0]))
                self.assertTrue(torch.equal(indices_tuple[2], shifted[2]))
                self.assertTrue(torch.equal(indices_tuple[1], shifted[1]-batch_size))
                self.assertTrue(torch.equal(indices_tuple[3], shifted[3]-batch_size))
                a1, p, a2, n = shifted
                self.assertTrue(not torch.any((all_labels[a1]-all_labels[p]).bool()))
                self.assertTrue(torch.all((all_labels[a2]-all_labels[n]).bool()))
                
                indices_tuple = pair_miner(embeddings, labels, self.loss.embedding_memory, self.loss.label_memory)
                shifted = c_f.shift_indices_tuple(indices_tuple, batch_size)
                self.assertTrue(torch.equal(indices_tuple[0], shifted[0]))
                self.assertTrue(torch.equal(indices_tuple[2], shifted[2]))
                self.assertTrue(torch.equal(indices_tuple[1], shifted[1]-batch_size))
                self.assertTrue(torch.equal(indices_tuple[3], shifted[3]-batch_size))
                a1, p, a2, n = shifted
                self.assertTrue(not torch.any((all_labels[a1]-all_labels[p]).bool()))
                self.assertTrue(torch.all((all_labels[a2]-all_labels[n]).bool()))

                indices_tuple = triplet_miner(embeddings, labels, self.loss.embedding_memory, self.loss.label_memory)
                shifted = c_f.shift_indices_tuple(indices_tuple, batch_size)
                self.assertTrue(torch.equal(indices_tuple[0], shifted[0]))
                self.assertTrue(torch.equal(indices_tuple[1], shifted[1]-batch_size))
                self.assertTrue(torch.equal(indices_tuple[2], shifted[2]-batch_size))
                a, p, n = shifted
                self.assertTrue(not torch.any((all_labels[a]-all_labels[p]).bool()))
                self.assertTrue(torch.all((all_labels[p]-all_labels[n]).bool()))


    def test_input_indices_tuple(self):
        for dtype in TEST_DTYPES:
            batch_size = 32
            pair_miner = PairMarginMiner(pos_margin=0, neg_margin=1)
            triplet_miner = TripletMarginMiner(margin=1)
            self.loss = CrossBatchMemory(loss=ContrastiveLoss(), embedding_size=self.embedding_size, memory_size=self.memory_size)
            for i in range(30):
                embeddings = torch.randn(batch_size, self.embedding_size).to(self.device).type(dtype)
                labels = torch.arange(batch_size).to(self.device)
                self.loss(embeddings, labels)
                for curr_miner in [pair_miner, triplet_miner]:
                    input_indices_tuple = curr_miner(embeddings, labels)
                    all_labels = torch.cat([labels, self.loss.label_memory], dim=0)
                    a1ii, pii, a2ii, nii = lmu.convert_to_pairs(input_indices_tuple, labels)
                    indices_tuple = lmu.get_all_pairs_indices(labels, self.loss.label_memory)
                    a1i, pi, a2i, ni = self.loss.remove_self_comparisons(indices_tuple)
                    a1, p, a2, n = self.loss.create_indices_tuple(batch_size, embeddings, labels, self.loss.embedding_memory, self.loss.label_memory, input_indices_tuple)
                    self.assertTrue(not torch.any((all_labels[a1]-all_labels[p]).bool()))
                    self.assertTrue(torch.all((all_labels[a2]-all_labels[n]).bool()))
                    self.assertTrue(len(a1) == len(a1i)+len(a1ii))
                    self.assertTrue(len(p) == len(pi)+len(pii))
                    self.assertTrue(len(a2) == len(a2i)+len(a2ii))
                    self.assertTrue(len(n) == len(ni)+len(nii))

